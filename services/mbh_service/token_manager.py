import json
from datetime import datetime, timedelta, timezone

from shared.database.connection import get_connection
from services.mbh_service.auth import refresh_psu_access_token


class MBHAuthenticationRequiredError(Exception):
    pass


API_TYPE_ACCOUNT_INFO = "ACCOUNT_INFO"


def _utc_now():
    return datetime.now(timezone.utc)


def _parse_dt(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def save_account_token_response(
    token_response_text: str,
    consent_id: str | None = None,
    consent_expires_at: str | None = None,
):
    data = json.loads(token_response_text)

    now = _utc_now()
    expires_in = int(data.get("expires_in", 0))
    access_token_expires_at = now + timedelta(seconds=expires_in)

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO mbh_auth_tokens (
                api_type,
                consent_id,
                consent_expires_at,
                access_token,
                refresh_token,
                access_token_expires_at,
                scope,
                token_type,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                API_TYPE_ACCOUNT_INFO,
                consent_id,
                consent_expires_at,
                data["access_token"],
                data.get("refresh_token"),
                access_token_expires_at.isoformat(),
                data.get("scope"),
                data.get("token_type"),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_account_token():
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM mbh_auth_tokens
            WHERE api_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (API_TYPE_ACCOUNT_INFO,),
        ).fetchone()

        return row
    finally:
        conn.close()


def get_valid_account_access_token() -> str:
    token = get_latest_account_token()

    if not token:
        raise MBHAuthenticationRequiredError("MBH engedélyezés szükséges.")

    expires_at = _parse_dt(token["access_token_expires_at"])

    if expires_at > _utc_now() + timedelta(seconds=30):
        return token["access_token"]

    refresh_token = token["refresh_token"]

    if not refresh_token:
        raise MBHAuthenticationRequiredError("MBH token lejárt, új engedélyezés szükséges.")

    status, text, _ = refresh_psu_access_token(refresh_token)

    if status != 200:
        raise MBHAuthenticationRequiredError(
            f"MBH token frissítés sikertelen: {text}"
        )

    save_account_token_response(
        text,
        consent_id=token["consent_id"],
        consent_expires_at=token["consent_expires_at"],
    )

    refreshed = get_latest_account_token()
    return refreshed["access_token"]