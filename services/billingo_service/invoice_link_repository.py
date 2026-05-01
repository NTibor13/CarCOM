from shared.database.connection import get_connection


ACTIVE_STATUSES = ("DRAFT_CREATED", "DRAFT_CONFIRMED")


def get_latest_invoice_link(transaction_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM billingo_invoice_links
            WHERE transaction_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (transaction_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def get_active_invoice_link(transaction_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT *
            FROM billingo_invoice_links
            WHERE transaction_id = ?
              AND status IN ({",".join(["?"] * len(ACTIVE_STATUSES))})
            ORDER BY id DESC
            LIMIT 1
            """,
            (transaction_id, *ACTIVE_STATUSES),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def create_invoice_link(
    transaction_id: int,
    billingo_document_id: int,
    billingo_document_number: str | None,
    status: str,
    api_log_id: int | None,
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO billingo_invoice_links (
                transaction_id,
                billingo_document_id,
                billingo_document_number,
                status,
                api_log_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                transaction_id,
                billingo_document_id,
                billingo_document_number,
                status,
                api_log_id,
            ),
        )
        link_id = cur.lastrowid
        conn.commit()
        return link_id


def mark_invoice_link_confirmed(link_id: int, api_log_id: int | None = None) -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE billingo_invoice_links
            SET status = 'DRAFT_CONFIRMED',
                api_log_id = COALESCE(?, api_log_id),
                last_checked_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (api_log_id, link_id),
        )
        conn.commit()


def mark_invoice_link_missing(link_id: int, api_log_id: int | None = None) -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE billingo_invoice_links
            SET status = 'DRAFT_MISSING',
                api_log_id = COALESCE(?, api_log_id),
                last_checked_at = CURRENT_TIMESTAMP,
                missing_detected_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (api_log_id, link_id),
        )
        conn.commit()