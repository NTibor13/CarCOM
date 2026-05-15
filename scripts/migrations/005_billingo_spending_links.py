from shared.database.connection import get_connection


def migrate() -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS billingo_spending_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                transaction_id INTEGER NOT NULL UNIQUE,
                batch_id INTEGER,

                billingo_spending_id INTEGER NOT NULL,
                status TEXT NOT NULL,

                api_log_id INTEGER,
                raw_response_json TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id),
                FOREIGN KEY(batch_id) REFERENCES payment_batches(id),
                FOREIGN KEY(api_log_id) REFERENCES api_call_logs(id)
            )
        """)

        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Migration completed: 005_billingo_spending_links")