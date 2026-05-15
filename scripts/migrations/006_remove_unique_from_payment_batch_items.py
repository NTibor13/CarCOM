from shared.database.connection import get_connection


def migrate() -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("PRAGMA foreign_keys=OFF")

        cur.execute("""
            ALTER TABLE payment_batch_items
            RENAME TO payment_batch_items_old
        """)

        cur.execute("""
            CREATE TABLE payment_batch_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                transaction_id INTEGER NOT NULL,
                creditor_name TEXT NOT NULL,
                creditor_bank_account TEXT NOT NULL,
                amount_huf INTEGER NOT NULL,
                payment_notice TEXT,
                status TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(batch_id) REFERENCES payment_batches(id),
                FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id)
            )
        """)

        cur.execute("""
            INSERT INTO payment_batch_items (
                id,
                batch_id,
                transaction_id,
                creditor_name,
                creditor_bank_account,
                amount_huf,
                payment_notice,
                status,
                created_at
            )
            SELECT
                id,
                batch_id,
                transaction_id,
                creditor_name,
                creditor_bank_account,
                amount_huf,
                payment_notice,
                status,
                created_at
            FROM payment_batch_items_old
        """)

        cur.execute("DROP TABLE payment_batch_items_old")

        cur.execute("PRAGMA foreign_keys=ON")

        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Migration completed: 006_remove_unique_from_payment_batch_items")