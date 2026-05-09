from shared.database.connection import get_connection
from services.flow_service.flow_engine import evaluate_transaction
from services.flow_service.flow_executor import FlowExecutor
from services.payment_batch_service.payment_batch_repository import PaymentBatchRepository


class PurchaseBatchExecutor:
    def __init__(self):
        self.payment_batch_repository = PaymentBatchRepository()
        self.flow_executor = FlowExecutor()

    def run(self, transaction_ids: list[int]) -> dict:
        if not transaction_ids:
            return {
                "status": "skipped",
                "reason": "no_transactions_selected",
                "payment_batch_id": None,
                "successful": [],
                "skipped": [],
                "failed": [],
            }

        ready_transaction_ids = []
        skipped = []

        for transaction_id in transaction_ids:
            transaction = self._get_transaction(transaction_id)

            if transaction is None:
                skipped.append({
                    "transaction_id": transaction_id,
                    "reason": "transaction_not_found",
                })
                continue

            flow_result = evaluate_transaction(transaction)

            if flow_result["action"] != "PURCHASE_PAYMENT_READY":
                skipped.append({
                    "transaction_id": transaction_id,
                    "reason": flow_result["reason"],
                })
                continue

            ready_transaction_ids.append(transaction_id)

        if not ready_transaction_ids:
            return {
                "status": "skipped",
                "reason": "no_ready_transactions",
                "payment_batch_id": None,
                "successful": [],
                "skipped": skipped,
                "failed": [],
            }

        payment_batch_id = self.payment_batch_repository.create_open_batch()

        successful = []
        failed = []

        for transaction_id in ready_transaction_ids:
            result = self.flow_executor.run_purchase_flow(
                transaction_id=transaction_id,
                force_new_run=True,
                payment_batch_id=payment_batch_id,
            )

            if result["status"] == "SUCCESS":
                successful.append({
                    "transaction_id": transaction_id,
                    "flow_run_id": result["flow_run_id"],
                })
            else:
                failed.append({
                    "transaction_id": transaction_id,
                    "result": result,
                })

        return {
            "status": "success" if successful else "failed",
            "payment_batch_id": payment_batch_id,
            "successful": successful,
            "skipped": skipped,
            "failed": failed,
        }

    def _get_transaction(self, transaction_id: int) -> dict | None:
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

        return dict(row) if row else None