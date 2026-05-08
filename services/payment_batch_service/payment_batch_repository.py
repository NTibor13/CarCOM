from shared.database.connection import get_connection


class PaymentBatchRepository:
    def get_or_create_open_batch(self) -> int:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id FROM payment_batches
                WHERE status = 'OPEN'
                ORDER BY id DESC
                LIMIT 1
            """)
            row = cur.fetchone()

            if row:
                return int(row["id"])

            cur.execute("""
                INSERT INTO payment_batches (status)
                VALUES ('OPEN')
            """)
            conn.commit()
            return int(cur.lastrowid)

    def create_or_get_item_for_transaction(self, transaction_id: int) -> dict:
        with get_connection() as conn:
            cur = conn.cursor()

            cur.execute("""
                SELECT * FROM payment_batch_items
                WHERE transaction_id = ?
            """, (transaction_id,))
            existing = cur.fetchone()
            if existing:
                return {
                    "status": "skipped",
                    "reason": "Payment batch item already exists",
                    "payment_batch_item_id": existing["id"],
                }

            cur.execute("""
                SELECT
                    id,
                    partner_name,
                    bank_account,
                    gross_amount_huf,
                    payment_notice
                FROM finance_transactions
                WHERE id = ?
            """, (transaction_id,))
            tx = cur.fetchone()

            if not tx:
                raise RuntimeError(f"Transaction not found: {transaction_id}")

            batch_id = self.get_or_create_open_batch()

            cur.execute("""
                INSERT INTO payment_batch_items (
                    batch_id,
                    transaction_id,
                    creditor_name,
                    creditor_bank_account,
                    amount_huf,
                    payment_notice,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                batch_id,
                transaction_id,
                tx["partner_name"],
                tx["bank_account"],
                tx["gross_amount_huf"],
                tx["payment_notice"],
                "CREATED",
            ))

            conn.commit()

            return {
                "status": "success",
                "payment_batch_id": batch_id,
                "payment_batch_item_id": cur.lastrowid,
            }