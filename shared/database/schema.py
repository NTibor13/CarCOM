from shared.database.connection import get_connection


def init_database() -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_identifier TEXT NOT NULL,
            rows_read INTEGER DEFAULT 0,
            inserted_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            deleted_count INTEGER DEFAULT 0,
            error_message TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sheet_rows_raw (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            row_hash TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(source_name, source_row_number)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sheet_row_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_row_id INTEGER,
            sync_run_id INTEGER NOT NULL,
            source_name TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            row_hash TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            change_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(sheet_row_id) REFERENCES sheet_rows_raw(id),
            FOREIGN KEY(sync_run_id) REFERENCES sync_runs(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS sheet_processing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_row_id INTEGER NOT NULL UNIQUE,
            source_name TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            flow_type TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(sheet_row_id) REFERENCES sheet_rows_raw(id)
        )
        """)


        cur.execute("""
        CREATE TABLE IF NOT EXISTS lookup_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            value TEXT NOT NULL,
            normalized_value TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_name, value)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS source_header_validation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            header_name TEXT NOT NULL,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_row_id INTEGER NOT NULL UNIQUE,
            source_row_number INTEGER NOT NULL,
            external_id INTEGER,
            transaction_date TEXT,
            source_account TEXT,
            gross_amount_huf INTEGER,
            vat_rate TEXT,
            net_amount_huf TEXT,
            source_cost_center TEXT,
            transaction_type TEXT NOT NULL,
            car_name TEXT,
            partner_name TEXT,
            bank_account TEXT,
            payment_notice TEXT,
            payment_deadline TEXT,
            invoice_status TEXT,
            payment_status TEXT,
            kg_debt_huf INTEGER,
            note TEXT,
            normalized_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(sheet_row_id) REFERENCES sheet_rows_raw(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_transaction_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            document_type TEXT NOT NULL,
            source_column TEXT NOT NULL,
            file_name TEXT,
            file_url TEXT,
            raw_value TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS finance_validation_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            sheet_row_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            error_code TEXT NOT NULL,
            error_message TEXT NOT NULL,
            severity TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id),
            FOREIGN KEY(sheet_row_id) REFERENCES sheet_rows_raw(id)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS api_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            transaction_id INTEGER,
            request_json TEXT,
            response_status INTEGER,
            response_json TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id)
        )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS billingo_invoice_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                billingo_document_id INTEGER NOT NULL,
                billingo_document_number TEXT,
                status TEXT NOT NULL,
                api_log_id INTEGER,
                last_checked_at TEXT,
                missing_detected_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(transaction_id) REFERENCES finance_transactions(id),
                FOREIGN KEY(api_log_id) REFERENCES api_call_logs(id)
            )
        """)

        _seed_lookup_values(cur)

        conn.commit()



def _seed_lookup_values(cur) -> None:
    values = [
        ("SOURCE_ACCOUNT", "Egyenleg", "Egyenleg"),
        ("VAT_RATE", "0%", "0"),
        ("VAT_RATE", "18%", "0.18"),
        ("VAT_RATE", "27%", "0.27"),
        ("KOLTSEGHELY_SOURCE", "Vétel", "PURCHASE"),
        ("KOLTSEGHELY_SOURCE", "Eladás", "SALE"),
        ("KOLTSEGHELY_SOURCE", "Eladás készlet 90 nap", "SALE_STOCK_90_DAYS"),
        ("KOLTSEGHELY_SOURCE", "Adminisztráció", "OTHER"),
        ("KOLTSEGHELY_SOURCE", "Egyéb", "OTHER"),
        ("KOLTSEGHELY_SOURCE", "Foglaló", "OTHER"),
        ("KOLTSEGHELY_SOURCE", "Felkészítés", "OTHER"),
        ("KOLTSEGHELY_SOURCE", "Bizományos értékesítés", "OTHER"),
        ("INVOICE_STATUS", "Számlára vár", "Számlára vár"),
        ("INVOICE_STATUS", "Számlázott", "Számlázott"),
        ("PAYMENT_STATUS", "Fizetésre vár (vétel)", "Fizetésre vár (vétel)"),
        ("PAYMENT_STATUS", "Fizetett (vétel)", "Fizetett (vétel)"),
        ("PAYMENT_STATUS", "Részben fizetett (vétel)", "Részben fizetett (vétel)"),
        ("PAYMENT_STATUS", "Kiegyenlítésre vár (eladás)", "Kiegyenlítésre vár (eladás)"),
        ("PAYMENT_STATUS", "Kiegyenlített (eladás)", "Kiegyenlített (eladás)"),
        ("PAYMENT_STATUS", "Részben kiegyenlített (eladás)", "Részben kiegyenlített (eladás)"),
    ]

    cur.executemany(
        """
        INSERT OR IGNORE INTO lookup_values (group_name, value, normalized_value)
        VALUES (?, ?, ?)
        """,
        values,
    )
