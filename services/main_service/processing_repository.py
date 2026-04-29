from datetime import datetime, timezone

from shared.database.connection import get_connection

SOURCE_NAME = "google_sheet_finance"
DEFAULT_FLOW_TYPE = "UNKNOWN"
DEFAULT_STATUS = "NEW"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProcessingRepository:
    def ensure_processing_items_for_active_rows(self) -> dict[str, int]:
        """
        Creates processing records for all active raw Sheet rows that do not yet
        have a processing item.

        This is intentionally business-logic-light: it only prepares the rows
        for later Main Service orchestration/validation.
        """
        created = 0
        skipped = 0

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, source_row_number
                FROM sheet_rows_raw
                WHERE source_name = ? AND is_active = 1
                ORDER BY source_row_number
                """,
                (SOURCE_NAME,),
            )
            rows = cur.fetchall()

            for row in rows:
                sheet_row_id = int(row["id"])
                source_row_number = int(row["source_row_number"])

                cur.execute(
                    """
                    SELECT id
                    FROM sheet_processing
                    WHERE sheet_row_id = ?
                    """,
                    (sheet_row_id,),
                )
                existing = cur.fetchone()

                if existing is not None:
                    skipped += 1
                    continue

                cur.execute(
                    """
                    INSERT INTO sheet_processing (
                        sheet_row_id,
                        source_name,
                        source_row_number,
                        flow_type,
                        status,
                        error_message,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        sheet_row_id,
                        SOURCE_NAME,
                        source_row_number,
                        DEFAULT_FLOW_TYPE,
                        DEFAULT_STATUS,
                        now_iso(),
                        now_iso(),
                    ),
                )
                created += 1

            conn.commit()

        return {"created": created, "skipped": skipped}

    def get_status_summary(self) -> list[dict[str, int | str]]:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT status, flow_type, COUNT(*) AS count
                FROM sheet_processing
                GROUP BY status, flow_type
                ORDER BY status, flow_type
                """
            )
            return [dict(row) for row in cur.fetchall()]
