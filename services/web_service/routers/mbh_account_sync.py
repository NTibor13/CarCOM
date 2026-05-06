from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta
import requests

from services.web_service.routers.mbh_account_settings import (
    get_valid_account_info_token,
    MBH_ACCOUNT_INFO_BASE_URL,
)

router = APIRouter(
    prefix="/settings/mbh/account-info/sync",
    tags=["Settings - MBH Account Info Sync"],
)


@router.post("/run")
def run_mbh_account_info_sync(days_back: int = 7):
    token = get_valid_account_info_token()

    accounts_response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts",
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30,
    )

    if accounts_response.status_code != 200:
        raise HTTPException(
            status_code=accounts_response.status_code,
            detail={
                "message": "MBH számlák lekérdezése sikertelen",
                "mbh_response": accounts_response.text,
            },
        )

    accounts_json = accounts_response.json()
    accounts = accounts_json.get("Data", {}).get("Account", [])

    from_dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    to_dt = datetime.now(timezone.utc)

    result = {
        "success": True,
        "synced_at": to_dt.isoformat(),
        "days_back": days_back,
        "accounts_count": len(accounts),
        "accounts": [],
    }

    for account in accounts:
        account_id = account.get("AccountId")

        if not account_id:
            continue

        balances = fetch_account_balances(token["access_token"], account_id)
        transactions = fetch_account_transactions(
            token["access_token"],
            account_id,
            from_dt.isoformat(),
            to_dt.isoformat(),
        )

        result["accounts"].append(
            {
                "account_id": account_id,
                "nickname": account.get("Nickname"),
                "currency": account.get("Currency"),
                "balances_count": len(
                    balances.get("Data", {}).get("Balance", [])
                ),
                "transactions_count": len(
                    transactions.get("Data", {}).get("Transaction", [])
                ),
                "balances": balances,
                "transactions": transactions,
            }
        )

    return result


def fetch_account_balances(access_token: str, account_id: str) -> dict:
    response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts/{account_id}/balances",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json; charset=utf-8",
        },
        timeout=30,
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code": response.status_code,
            "response": response.text,
        }

    return response.json()


def fetch_account_transactions(
    access_token: str,
    account_id: str,
    from_booking_date_time: str,
    to_booking_date_time: str,
) -> dict:
    response = requests.get(
        f"{MBH_ACCOUNT_INFO_BASE_URL}/accounts/{account_id}/transactions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json; charset=utf-8",
        },
        params={
            "fromBookingDateTime": from_booking_date_time,
            "toBookingDateTime": to_booking_date_time,
        },
        timeout=30,
    )

    if response.status_code != 200:
        return {
            "error": True,
            "status_code": response.status_code,
            "response": response.text,
        }

    return response.json()