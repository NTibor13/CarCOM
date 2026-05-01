import json
from datetime import datetime
from typing import Any

from shared.database.connection import get_connection


def _now() -> str:
    return datetime.utcnow().isoformat()


class FlowRepository:
    def get_or_create_flow_run(self, transaction_id: int, flow_type: str) -> dict:
        now = _now()

        with get_connection() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT *
                FROM flow_runs
                WHERE transaction_id = ?
                  AND flow_type = ?
                """,
                (transaction_id, flow_type),
            )
            existing = cur.fetchone()

            if existing:
                return dict(existing)

            cur.execute(
                """
                INSERT INTO flow_runs (
                    transaction_id,
                    flow_type,
                    status,
                    started_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    flow_type,
                    "RUNNING",
                    now,
                    now,
                    now,
                ),
            )

            conn.commit()

            cur.execute(
                """
                SELECT *
                FROM flow_runs
                WHERE id = ?
                """,
                (cur.lastrowid,),
            )

            return dict(cur.fetchone())

    def mark_flow_running(self, flow_run_id: int) -> None:
        now = _now()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_runs
                SET status = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                ("RUNNING", now, flow_run_id),
            )
            conn.commit()

    def mark_flow_success(self, flow_run_id: int) -> None:
        now = _now()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_runs
                SET status = ?,
                    finished_at = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                ("SUCCESS", now, now, flow_run_id),
            )
            conn.commit()

    def mark_flow_failed(self, flow_run_id: int, error_message: str) -> None:
        now = _now()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_runs
                SET status = ?,
                    finished_at = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                ("FAILED", now, error_message, now, flow_run_id),
            )
            conn.commit()

    def get_step_log(self, flow_run_id: int, step_name: str) -> dict | None:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT *
                FROM flow_step_logs
                WHERE flow_run_id = ?
                  AND step_name = ?
                """,
                (flow_run_id, step_name),
            )
            row = cur.fetchone()

            return dict(row) if row else None

    def start_step(
        self,
        flow_run_id: int,
        step_name: str,
        step_order: int,
        input_data: dict[str, Any] | None = None,
    ) -> None:
        now = _now()
        input_json = json.dumps(input_data or {}, ensure_ascii=False)

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO flow_step_logs (
                    flow_run_id,
                    step_name,
                    step_order,
                    status,
                    started_at,
                    input_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(flow_run_id, step_name)
                DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at,
                    finished_at = NULL,
                    input_json = excluded.input_json,
                    output_json = NULL,
                    error_message = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    flow_run_id,
                    step_name,
                    step_order,
                    "RUNNING",
                    now,
                    input_json,
                    now,
                    now,
                ),
            )
            conn.commit()

    def mark_step_success(
        self,
        flow_run_id: int,
        step_name: str,
        output_data: dict[str, Any] | None = None,
    ) -> None:
        now = _now()
        output_json = json.dumps(output_data or {}, ensure_ascii=False)

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_step_logs
                SET status = ?,
                    finished_at = ?,
                    output_json = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE flow_run_id = ?
                  AND step_name = ?
                """,
                (
                    "SUCCESS",
                    now,
                    output_json,
                    now,
                    flow_run_id,
                    step_name,
                ),
            )
            conn.commit()

    def mark_step_failed(
        self,
        flow_run_id: int,
        step_name: str,
        error_message: str,
    ) -> None:
        now = _now()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_step_logs
                SET status = ?,
                    finished_at = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE flow_run_id = ?
                  AND step_name = ?
                """,
                (
                    "FAILED",
                    now,
                    error_message,
                    now,
                    flow_run_id,
                    step_name,
                ),
            )
            conn.commit()

    def mark_flow_skipped(self, flow_run_id: int, reason: str | None = None) -> None:
        now = _now()

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_runs
                SET status = ?,
                    finished_at = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                ("SKIPPED", now, reason, now, flow_run_id),
            )
            conn.commit()

    def mark_step_skipped(
        self,
        flow_run_id: int,
        step_name: str,
        output_data: dict[str, Any] | None = None,
    ) -> None:
        now = _now()
        output_json = json.dumps(output_data or {}, ensure_ascii=False)

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE flow_step_logs
                SET status = ?,
                    finished_at = ?,
                    output_json = ?,
                    error_message = NULL,
                    updated_at = ?
                WHERE flow_run_id = ?
                  AND step_name = ?
                """,
                (
                    "SKIPPED",
                    now,
                    output_json,
                    now,
                    flow_run_id,
                    step_name,
                ),
            )
            conn.commit()