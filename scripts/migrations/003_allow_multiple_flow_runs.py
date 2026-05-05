from shared.database.connection import get_connection


def migrate() -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("PRAGMA foreign_keys=off")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS flow_runs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                flow_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id)
            )
        """)

        cur.execute("""
            INSERT INTO flow_runs_new (
                id,
                transaction_id,
                flow_type,
                status,
                started_at,
                finished_at,
                error_message,
                created_at,
                updated_at
            )
            SELECT
                id,
                transaction_id,
                flow_type,
                status,
                started_at,
                finished_at,
                error_message,
                created_at,
                updated_at
            FROM flow_runs
        """)

        cur.execute("DROP TABLE flow_runs")
        cur.execute("ALTER TABLE flow_runs_new RENAME TO flow_runs")

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_runs_transaction
            ON flow_runs(transaction_id, flow_type)
        """)

        cur.execute("PRAGMA foreign_keys=on")
        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Migration completed: multiple flow runs enabled.")