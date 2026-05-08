from shared.database.connection import get_connection
from services.payment_batch_service.payment_batch_repository import PaymentBatchRepository
from services.sync_service.google_sheets_client import GoogleSheetsClient


def create_payment_batch_item_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    return PaymentBatchRepository().create_or_get_item_for_transaction(transaction_id)


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