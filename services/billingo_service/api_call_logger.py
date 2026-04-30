import json
from shared.database.connection import get_connection


def log_api_call(
    provider: str,
    endpoint: str,
    method: str,
    transaction_id: int | None,
    request_payload: dict | None,
    response_status: int | None,
    response_payload: dict | None,
    success: bool,
    error_message: str | None = None,
) -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO api_call_logs (
                provider,
                endpoint,
                method,
                transaction_id,
                request_json,
                response_status,
                response_json,
                success,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                endpoint,
                method,
                transaction_id,
                json.dumps(request_payload, ensure_ascii=False) if request_payload else None,
                response_status,
                json.dumps(response_payload, ensure_ascii=False) if response_payload else None,
                1 if success else 0,
                error_message,
            ),
        )
        conn.commit()