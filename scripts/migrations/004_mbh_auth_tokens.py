from shared.database.connection import get_connection


def run():
    conn = get_connection()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mbh_auth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_type TEXT NOT NULL,
                consent_id TEXT,
                consent_expires_at TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                access_token_expires_at TEXT NOT NULL,
                scope TEXT,
                token_type TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )

        conn.commit()
        print("MBH auth tokens table created")

    finally:
        conn.close()

if __name__ == "__main__":
    run()