import json
from datetime import datetime, timezone
from typing import Any

from shared.config.settings import settings
from shared.database.connection import get_connection

SERVICE_NAME = "carcom-sync-service"
SOURCE_NAME = "google_sheet_finance"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncRepository:
    def create_sync_run(self) -> int:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO sync_runs (
                    service_name,
                    started_at,
                    status,
                    source_name,
                    source_identifier
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    SERVICE_NAME,
                    now_iso(),
                    "running",
                    SOURCE_NAME,
                    f"{settings.google_sheet_id}/{settings.google_worksheet_name}",
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def finish_sync_run(
        self,
        sync_run_id: int,
        status: str,
        rows_read: int = 0,
        inserted_count: int = 0,
        updated_count: int = 0,
        deleted_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?,
                    status = ?,
                    rows_read = ?,
                    inserted_count = ?,
                    updated_count = ?,
                    deleted_count = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    now_iso(),
                    status,
                    rows_read,
                    inserted_count,
                    updated_count,
                    deleted_count,
                    error_message,
                    sync_run_id,
                ),
            )
            conn.commit()

    def sync_rows(self, sync_run_id: int, rows: list[dict[str, Any]], hash_factory) -> dict[str, int]:
        inserted = 0
        updated = 0
        deleted = 0
        current_source_rows = set()

        with get_connection() as conn:
            cur = conn.cursor()

            for item in rows:
                source_row_number = int(item["source_row_number"])
                row_data = item["data"]
                current_source_rows.add(source_row_number)

                row_hash = hash_factory(row_data)
                raw_json = json.dumps(row_data, ensure_ascii=False, sort_keys=True)

                cur.execute(
                    """
                    SELECT id, row_hash
                    FROM sheet_rows_raw
                    WHERE source_name = ? AND source_row_number = ?
                    """,
                    (SOURCE_NAME, source_row_number),
                )
                existing = cur.fetchone()

                if existing is None:
                    cur.execute(
                        """
                        INSERT INTO sheet_rows_raw (
                            source_name,
                            source_row_number,
                            row_hash,
                            raw_json,
                            first_seen_at,
                            last_seen_at,
                            is_active
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        """,
                        (SOURCE_NAME, source_row_number, row_hash, raw_json, now_iso(), now_iso()),
                    )
                    sheet_row_id = int(cur.lastrowid)
                    self._insert_version(cur, sheet_row_id, sync_run_id, source_row_number, row_hash, raw_json, "inserted")
                    inserted += 1
                    continue

                sheet_row_id = int(existing["id"])
                existing_hash = existing["row_hash"]

                if existing_hash != row_hash:
                    cur.execute(
                        """
                        UPDATE sheet_rows_raw
                        SET row_hash = ?, raw_json = ?, last_seen_at = ?, is_active = 1
                        WHERE id = ?
                        """,
                        (row_hash, raw_json, now_iso(), sheet_row_id),
                    )
                    self._insert_version(cur, sheet_row_id, sync_run_id, source_row_number, row_hash, raw_json, "updated")
                    updated += 1
                else:
                    cur.execute(
                        """
                        UPDATE sheet_rows_raw
                        SET last_seen_at = ?, is_active = 1
                        WHERE id = ?
                        """,
                        (now_iso(), sheet_row_id),
                    )

            cur.execute(
                """
                SELECT id, source_row_number, row_hash, raw_json
                FROM sheet_rows_raw
                WHERE source_name = ? AND is_active = 1
                """,
                (SOURCE_NAME,),
            )
            active_rows = cur.fetchall()

            for active_row in active_rows:
                source_row_number = int(active_row["source_row_number"])
                if source_row_number not in current_source_rows:
                    sheet_row_id = int(active_row["id"])
                    cur.execute(
                        """
                        UPDATE sheet_rows_raw
                        SET is_active = 0, last_seen_at = ?
                        WHERE id = ?
                        """,
                        (now_iso(), sheet_row_id),
                    )
                    self._insert_version(
                        cur,
                        sheet_row_id,
                        sync_run_id,
                        source_row_number,
                        active_row["row_hash"],
                        active_row["raw_json"],
                        "deleted",
                    )
                    deleted += 1

            conn.commit()

        return {"inserted": inserted, "updated": updated, "deleted": deleted}

    def _insert_version(
        self,
        cur,
        sheet_row_id: int,
        sync_run_id: int,
        source_row_number: int,
        row_hash: str,
        raw_json: str,
        change_type: str,
    ) -> None:
        cur.execute(
            """
            INSERT INTO sheet_row_versions (
                sheet_row_id,
                sync_run_id,
                source_name,
                source_row_number,
                row_hash,
                raw_json,
                change_type,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sheet_row_id, sync_run_id, SOURCE_NAME, source_row_number, row_hash, raw_json, change_type, now_iso()),
        )
