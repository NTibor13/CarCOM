from shared.database.connection import get_connection


def migrate() -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("PRAGMA foreign_keys=OFF")

        cur.execute("""
            ALTER TABLE billingo_spending_links
            RENAME TO billingo_spending_links_old
        """)

        cur.execute("""
            CREATE TABLE billingo_spending_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                transaction_id INTEGER NOT NULL,
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

        cur.execute("""
            INSERT INTO billingo_spending_links (
                id,
                transaction_id,
                batch_id,
                billingo_spending_id,
                status,
                api_log_id,
                raw_response_json,
                created_at,
                updated_at
            )
            SELECT
                id,
                transaction_id,
                batch_id,
                billingo_spending_id,
                status,
                api_log_id,
                raw_response_json,
                created_at,
                updated_at
            FROM billingo_spending_links_old
        """)

        cur.execute("DROP TABLE billingo_spending_links_old")

        cur.execute("PRAGMA foreign_keys=ON")

        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Migration completed: 007_remove_unique_from_billingo_spending_links")