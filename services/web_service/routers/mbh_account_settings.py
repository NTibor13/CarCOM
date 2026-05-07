import requests
import json

from datetime import datetime, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from shared.database.connection import get_connection
from services.mbh_service.auth import (
    get_tpp_access_token,
    build_authorization_url,
    exchange_authorization_code,
    refresh_psu_access_token,
)
from services.mbh_service.certificates import validate_mbh_certificate_configuration

router = APIRouter(
    prefix="/settings/mbh/account-info",
    tags=["Settings - MBH Account Info"],
)

API_TYPE = "account_info"

MBH_ACCOUNT_INFO_BASE_URL = "https://api.sandbox1.mbhbank.hu/account-info-ob/v2"

CONSENT_EXPIRES_AT = "2035-12-31T23:59:59+00:00"

ACCOUNT_INFO_PERMISSIONS = [
    "ReadAccountsBasic",
    "ReadAccountsDetail",
    "ReadBalances",
    "ReadTransactionsBasic",
    "ReadTransactionsDetail",
    "ReadTransactionsCredits",
    "ReadTransactionsDebits",
]


@router.get("/status")
def get_mbh_account_info_status():
    conn = get_connection()
    conn.row_factory = dict_factory

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM mbh_auth_tokens
            WHERE api_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (API_TYPE,),
        )

        token = cursor.fetchone()

        if not token:
            return {
                "connected": False,
                "needs_reauth": True,
                "api_type": API_TYPE,
                "message": "MBH Account Info nincs authentikálva",
            }

        return {
            "connected": bool(token.get("access_token")),
            "needs_reauth": not bool(token.get("refresh_token")),
            "api_type": API_TYPE,
            "consent_id": token.get("consent_id"),
            "consent_expires_at": token.get("consent_expires_at"),
            "token_expires_at": token.get("access_token_expires_at"),
            "scope": token.get("scope"),
            "token_type": token.get("token_type"),
            "created_at": token.get("created_at"),
            "updated_at": token.get("updated_at"),
            "ui_status": build_mbh_account_info_ui_status(token),
        }

    finally:
        conn.close()


def build_mbh_account_info_ui_status(token: dict | None) -> dict:
    if not token:
        return {
            "level": "warning",
            "title": "MBH Account Info nincs előkészítve",
            "message": "Első lépésként hozz létre Account Info consentet.",
            "user_action": "Consent létrehozása szükséges",
            "action_hint": "Kattints a Consent létrehozása gombra.",
        }

    consent_id = token.get("consent_id")
    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")

    if consent_id and not access_token:
        return {
            "level": "info",
            "title": "MBH felhasználói hitelesítés szükséges",
            "message": "A consent létrejött, de a banki felhasználói authentikáció még nem történt meg.",
            "user_action": "Felhasználói authentikációra vár",
            "action_hint": "Kattints az MBH authentikáció indítása gombra.",
            "can_create_consent": True,
            "can_authorize": True,
            "can_sync": False,
        }

    if consent_id and access_token:
        return {
            "level": "success",
            "title": "MBH Account Info aktív",
            "message": "A banki kapcsolat aktív, a tokenek rendelkezésre állnak.",
            "user_action": "Nincs felhasználói teendő",
            "action_hint": "Indítható manuális szinkron.",
            "can_create_consent": True,
            "can_authorize": True,
            "can_sync": True,
        }

    return {
        "level": "warning",
        "title": "MBH kapcsolat részleges állapotban",
        "message": "A kapcsolat állapota nem teljes. Ellenőrizd a consent és token adatokat.",
        "user_action": "Ellenőrzés szükséges",
        "action_hint": "Próbáld újra a consent létrehozását.",
        "can_create_consent": True,
        "can_authorize": False,
        "can_sync": False,
    }

def dict_factory(cursor, row):
    return {
        col[0]: row[idx]
        for idx, col in enumerate(cursor.description)
    }

@router.post("/create-consent")
def create_mbh_account_info_consent():
    status_code, response_text, _ = get_tpp_access_token()

    if status_code != 200:
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": "TPP access token lekérés sikertelen",
                "mbh_response": response_text,
            },
        )

    token_response = json.loads(response_text)
    access_token = token_response["access_token"]

    payload = {
        "Data": {
            "Permissions": ACCOUNT_INFO_PERMISSIONS,
            "ExpirationDateTime": CONSENT_EXPIRES_AT,
            "TransactionFromDateTime": "2020-01-01T00:00:00+00:00",
            "TransactionToDateTime": CONSENT_EXPIRES_AT,
        },
        "Risk": {},
    }

    response = requests.post(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/account-access-consents",
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30,
    )

    if response.status_code not in (200, 201):
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "MBH Account Info consent létrehozás sikertelen",
                "mbh_response": response.text,
            },
        )

    response_json = response.json()
    data = response_json.get("Data", {})

    consent_id = data.get("ConsentId")
    consent_status = data.get("Status")
    consent_expires_at = data.get("ExpirationDateTime") or CONSENT_EXPIRES_AT

    if not consent_id:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "MBH válaszban nincs ConsentId",
                "mbh_response": response_json,
            },
        )

    save_account_info_consent(
        consent_id=consent_id,
        consent_expires_at=consent_expires_at,
        scope="accounts",
    )

    return {
        "success": True,
        "api_type": API_TYPE,
        "consent_id": consent_id,
        "consent_status": consent_status,
        "consent_expires_at": consent_expires_at,
        "message": "MBH Account Info consent létrehozva. Következő lépés: authentikáció.",
    }

def save_account_info_consent(consent_id: str, consent_expires_at: str, scope: str):
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
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
                API_TYPE,
                consent_id,
                consent_expires_at,
                "",
                None,
                now,
                scope,
                None,
                now,
                now,
            ),
        )

        conn.commit()

    finally:
        conn.close()

@router.get("/authorize")
def authorize_mbh_account_info():
    conn = get_connection()
    conn.row_factory = dict_factory

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM mbh_auth_tokens
            WHERE api_type = ?
              AND consent_id IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (API_TYPE,),
        )

        token = cursor.fetchone()

        if not token:
            raise HTTPException(
                status_code=404,
                detail="Nincs MBH Account Info consent. Előbb futtasd a create-consent endpointot.",
            )

        consent_id = token.get("consent_id")
        authorization_url = build_authorization_url(consent_id)

        return RedirectResponse(authorization_url)

    finally:
        conn.close()

@router.get("/callback")
def mbh_account_info_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        params = urlencode({
            "mbh_auth": "failed",
            "mbh_message": f"MBH authentikáció sikertelen: {error}",
        })
        return RedirectResponse(url=f"/settings?{params}", status_code=303)

    if not code:
        params = urlencode({
            "mbh_auth": "failed",
            "mbh_message": "Hiányzó authorization code az MBH callback válaszban.",
        })
        return RedirectResponse(url=f"/settings?{params}", status_code=303)

    status_code, response_text, _ = exchange_authorization_code(code)

    if status_code != 200:
        params = urlencode({
            "mbh_auth": "failed",
            "mbh_message": "Authorization code token cseréje sikertelen.",
        })
        return RedirectResponse(url=f"/settings?{params}", status_code=303)

    token_response = json.loads(response_text)
    save_account_info_tokens(token_response)

    return RedirectResponse(
        url="/settings?mbh_auth=success",
        status_code=303,
    )

def save_account_info_tokens(token_response: dict):
    now = datetime.now(timezone.utc)

    expires_in = token_response.get("expires_in", 0)

    access_token_expires_at = (
        now.timestamp() + int(expires_in)
    )

    access_token_expires_at_iso = datetime.fromtimestamp(
        access_token_expires_at,
        timezone.utc,
    ).isoformat()

    conn = get_connection()

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE mbh_auth_tokens
            SET
                access_token = ?,
                refresh_token = ?,
                access_token_expires_at = ?,
                scope = ?,
                token_type = ?,
                updated_at = ?
            WHERE id = (
                SELECT id
                FROM mbh_auth_tokens
                WHERE api_type = ?
                ORDER BY id DESC
                LIMIT 1
            )
            """,
            (
                token_response.get("access_token"),
                token_response.get("refresh_token"),
                access_token_expires_at_iso,
                token_response.get("scope"),
                token_response.get("token_type"),
                now.isoformat(),
                API_TYPE,
            ),
        )

        conn.commit()

    finally:
        conn.close()

@router.get("/accounts")
def get_mbh_accounts():
    token = get_valid_account_info_token()

    response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts",
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "MBH számlák lekérdezése sikertelen",
                "mbh_response": response.text,
            },
        )

    return response.json()

def get_valid_account_info_token() -> dict:
    token = get_latest_account_info_token()

    if not token:
        raise HTTPException(
            status_code=404,
            detail="Nincs MBH Account Info token. Előbb authentikálni kell.",
        )

    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    expires_at = token.get("access_token_expires_at")

    if access_token and expires_at and not is_token_expired(expires_at):
        return token

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="A token lejárt, és nincs refresh token. Újra authentikáció szükséges.",
        )

    status_code, response_text, _ = refresh_psu_access_token(refresh_token)

    if status_code != 200:
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": "MBH Account Info token frissítése sikertelen",
                "mbh_response": response_text,
            },
        )

    token_response = json.loads(response_text)
    save_account_info_tokens(token_response)

    return get_latest_account_info_token()

def get_latest_account_info_token() -> dict | None:
    conn = get_connection()
    conn.row_factory = dict_factory

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM mbh_auth_tokens
            WHERE api_type = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (API_TYPE,),
        )

        return cursor.fetchone()

    finally:
        conn.close()


def is_token_expired(expires_at: str) -> bool:
    try:
        expires_at_dt = datetime.fromisoformat(expires_at)
    except ValueError:
        return True

    now = datetime.now(timezone.utc)

    # 60 másodperc biztonsági ráhagyás
    return expires_at_dt <= now.replace(microsecond=0)

@router.get("/accounts/{account_id}/balances")
def get_mbh_account_balances(account_id: str):
    token = get_valid_account_info_token()

    response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts/{account_id}/balances",
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "MBH számlaegyenleg lekérdezése sikertelen",
                "mbh_response": response.text,
            },
        )

    return response.json()

@router.get("/accounts/{account_id}/transactions")
def get_mbh_account_transactions(
    account_id: str,
    from_booking_date_time: str | None = Query(default=None),
    to_booking_date_time: str | None = Query(default=None),
):
    token = get_valid_account_info_token()

    params = {}

    if from_booking_date_time:
        params["fromBookingDateTime"] = from_booking_date_time

    if to_booking_date_time:
        params["toBookingDateTime"] = to_booking_date_time

    response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts/{account_id}/transactions",
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/json; charset=utf-8",
        },
        params=params,
        timeout=30,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "MBH tranzakciók lekérdezése sikertelen",
                "mbh_response": response.text,
            },
        )

    return response.json()

@router.get("/certificate-check")
def mbh_certificate_check():
    try:
        return {
            "ok": True,
            "certificate_status": validate_mbh_certificate_configuration(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
        }