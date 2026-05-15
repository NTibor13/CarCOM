from shared.database.connection import get_connection
from services.payment_batch_service.payment_batch_repository import PaymentBatchRepository
from services.sync_service.google_sheets_client import GoogleSheetsClient
from services.payment_batch_service.mbh_huf_xml_101_exporter import (
    export_batch_to_mbh_huf_xml_101,
)
from services.billingo_service.spending_service import create_spendings_for_batch
from shared.config.settings import settings


def create_payment_batch_item_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    batch_id = context.get("payment_batch_id")
    force_new_run = bool(context.get("force_new_run"))

    repo = PaymentBatchRepository()

    if force_new_run:
        result = repo.create_new_item_for_transaction(
            transaction_id=transaction_id,
            batch_id=batch_id,
        )
    else:
        result = repo.create_or_get_item_for_transaction(
            transaction_id=transaction_id,
            batch_id=batch_id,
        )

    payment_batch_id = (
            result.get("batch_id")
            or result.get("payment_batch_id")
            or result.get("id")
    )

    if not payment_batch_id and result.get("payment_batch_item_id"):
        payment_batch_id = _get_batch_id_for_item(
            int(result["payment_batch_item_id"])
        )

    if not payment_batch_id:
        raise RuntimeError(
            f"Payment batch id not returned for transaction: {transaction_id}. "
            f"Repository result: {result}"
        )

    export_result = export_batch_to_mbh_huf_xml_101(
        batch_id=int(payment_batch_id),
        debtor_account=settings.default_payment_account,
        debtor_name=settings.company_name,
    )

    result["payment_batch_id"] = int(payment_batch_id)
    result["payment_export"] = export_result

    return result


def update_sheet_purchase_payment_status_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    transaction = _get_transaction(transaction_id)

    target_payment_status = "Fizetett (vétel)"

    if transaction.get("payment_status") == target_payment_status:
        return {
            "status": "already_updated",
            "payment_status": target_payment_status,
        }

    row_number = int(transaction["source_row_number"])

    GoogleSheetsClient().update_row_values(
        row_number=row_number,
        values_by_header={
            "Státusz fizetés": target_payment_status,
        },
    )

    _update_local_payment_status(
        transaction_id=transaction_id,
        payment_status=target_payment_status,
    )

    return {
        "status": "updated",
        "row_number": row_number,
        "payment_status": target_payment_status,
    }


def _get_transaction(transaction_id: int) -> dict:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise RuntimeError(f"Transaction not found: {transaction_id}")

    return dict(row)


def _update_local_payment_status(
    transaction_id: int,
    payment_status: str,
) -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE finance_transactions
            SET
                payment_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                payment_status,
                transaction_id,
            ),
        )
        conn.commit()

def _get_batch_id_for_item(payment_batch_item_id: int) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT batch_id
            FROM payment_batch_items
            WHERE id = ?
            """,
            (payment_batch_item_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise RuntimeError(f"Payment batch item not found: {payment_batch_item_id}")

    return int(row["batch_id"])

def create_billingo_spending_step(context: dict) -> dict:
    payment_batch_id = context.get("payment_batch_id")

    if not payment_batch_id:
        return {
            "status": "skipped",
            "reason": "missing_payment_batch_id",
        }

    spending_result = create_spendings_for_batch(
        int(payment_batch_id),
        force_new_run=bool(context.get("force_new_run")),
    )

    if spending_result.get("status") == "partial_failed":
        raise RuntimeError(f"Billingo spending creation failed: {spending_result}")

    return {
        "status": spending_result.get("status", "success"),
        "payment_batch_id": payment_batch_id,
        "billingo_spending": spending_result,
    }