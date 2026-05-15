import json

from shared.database.connection import get_connection


class SpendingLinkRepository:
    def get_by_transaction_id(self, transaction_id: int):
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT *
                FROM billingo_spending_links
                WHERE transaction_id = ?
            """, (transaction_id,))
            return cur.fetchone()

    def create(
        self,
        transaction_id: int,
        batch_id: int,
        billingo_spending_id: int,
        status: str,
        raw_response: dict,
        api_log_id: int | None = None,
    ) -> int:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO billingo_spending_links (
                    transaction_id,
                    batch_id,
                    billingo_spending_id,
                    status,
                    api_log_id,
                    raw_response_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                transaction_id,
                batch_id,
                billingo_spending_id,
                status,
                api_log_id,
                json.dumps(raw_response, ensure_ascii=False),
            ))

            conn.commit()
            return int(cur.lastrowid)