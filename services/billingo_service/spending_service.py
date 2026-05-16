import json
from datetime import date

from shared.database.connection import get_connection
from services.billingo_service.billingo_client import create_spending
from services.billingo_service.spending_link_repository import SpendingLinkRepository
from services.billingo_service.api_call_logger import log_api_call
from services.billingo_service.billingo_client import BillingoApiError


STEP_NAME = "CREATE_BILLINGO_SPENDING"


def create_spendings_for_batch(batch_id: int, force_new_run: bool = False) -> dict:
    batch = _load_batch(batch_id)

    if not batch:
        raise RuntimeError(f"Payment batch not found: {batch_id}")

    if batch["status"] != "XML_DONE":
        return {
            "status": "skipped",
            "reason": "batch_not_xml_done",
            "payment_batch_id": batch_id,
        }

    transactions = _load_individual_purchase_transactions(batch_id)

    if not transactions:
        return {
            "status": "skipped",
            "reason": "no_purchase_from_individual_items",
            "payment_batch_id": batch_id,
        }

    repo = SpendingLinkRepository()

    created = []
    skipped = []
    failed = []

    for tx in transactions:
        transaction_id = int(tx["id"])

        existing = repo.get_by_transaction_id(transaction_id)

        if existing and not force_new_run:
            skipped.append({
                "transaction_id": transaction_id,
                "reason": "billingo_spending_already_exists",
                "billingo_spending_id": existing["billingo_spending_id"],
            })
            continue

        try:
            payload = _build_spending_payload(tx)
            response = create_spending(payload)

            log_api_call(
                provider="Billingo",
                endpoint="/spendings",
                method="POST",
                transaction_id=transaction_id,
                request_payload=payload,
                response_status=201,
                response_payload=response,
                success=True,
            )

            billingo_spending_id = _extract_spending_id(response)
            repo.create(
                transaction_id=transaction_id,
                batch_id=batch_id,
                billingo_spending_id=billingo_spending_id,
                status="CREATED",
                raw_response=response,
            )
            created.append({
                "transaction_id": transaction_id,
                "billingo_spending_id": billingo_spending_id,
            })

        except BillingoApiError as exc:
            log_api_call(
                provider="Billingo",
                endpoint="/spendings",
                method="POST",
                transaction_id=transaction_id,
                request_payload=payload if "payload" in locals() else None,
                response_status=exc.status_code,
                response_payload=exc.response_data,
                success=False,
                error_message=str(exc),
            )
            failed.append({
                "transaction_id": transaction_id,
                "error": str(exc),
            })

        except Exception as exc:
            log_api_call(
                provider="Billingo",
                endpoint="/spendings",
                method="POST",
                transaction_id=transaction_id,
                request_payload=payload if "payload" in locals() else None,
                response_status=None,
                response_payload=None,
                success=False,
                error_message=str(exc),
            )
            failed.append({
                "transaction_id": transaction_id,
                "error": str(exc),
            })

    return {
        "status": "success" if not failed else "partial_failed",
        "payment_batch_id": batch_id,
        "created": created,
        "skipped": skipped,
        "failed": failed,
    }


def _load_batch(batch_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT *
            FROM payment_batches
            WHERE id = ?
        """, (batch_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _load_individual_purchase_transactions(batch_id: int) -> list[dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                ft.*
            FROM payment_batch_items pbi
            JOIN finance_transactions ft ON ft.id = pbi.transaction_id
            WHERE pbi.batch_id = ?
              AND ft.transaction_type = 'PURCHASE FROM INDIVIDUAL'
            ORDER BY ft.id
        """, (batch_id,))

        return [dict(row) for row in cur.fetchall()]


def _build_spending_payload(tx: dict) -> dict:
    from datetime import date, datetime, timedelta

    transaction_date_raw = tx.get("transaction_date")
    transaction_date = transaction_date_raw or date.today().isoformat()

    try:
        fulfillment_date = datetime.fromisoformat(transaction_date).date()
    except ValueError:
        fulfillment_date = date.today()

    invoice_date = date.today()
    due_date = fulfillment_date + timedelta(days=3)

    gross_amount = int(round(float(tx.get("gross_amount_huf") or 0)))
    vat_rate = float(tx.get("vat_rate") or 0)

    if gross_amount <= 0:
        raise RuntimeError(f"Invalid gross amount for transaction {tx.get('id')}")

    if vat_rate == 0:
        vat_label = "0%"
        total_vat_amount = 0
    else:
        vat_label = f"{int(round(vat_rate * 100))}%"
        net_amount = gross_amount / (1 + vat_rate)
        total_vat_amount = int(round(gross_amount - net_amount))

    car_name = tx.get("car_name") or "Gépjármű"
    payment_notice = tx.get("payment_notice") or f"{car_name} VÉTELÁR"

    return {
        "currency": "HUF",
        "conversion_rate": 1,

        "total_gross": gross_amount,
        "total_gross_huf": gross_amount,
        "total_vat_amount": total_vat_amount,
        "total_vat_amount_huf": total_vat_amount,

        "fulfillment_date": fulfillment_date.isoformat(),
        "category": "stock",
        "comment": (
            f"Terméknév: Gépjármű ({car_name}) - "
            f"Bruttó egységár: {gross_amount} Ft - "
            f"Áfa kulcs: {vat_label} - "
            f"Mennyiség: 1 db"
        ),
        "invoice_number": payment_notice,
        "invoice_date": invoice_date.isoformat(),
        "due_date": due_date.isoformat(),
        "payment_method": "wire_transfer",
    }


def _extract_spending_id(response: dict) -> int:
    for key in ("id", "spending_id", "spendingId"):
        value = response.get(key)
        if value:
            return int(value)

    raise RuntimeError(f"Billingo spending id not found in response: {json.dumps(response, ensure_ascii=False)}")
    raise RuntimeError(f"Billingo spending id not found in response: {json.dumps(response, ensure_ascii=False)}")