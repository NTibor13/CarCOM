import json
import uuid
import requests
from datetime import datetime, timedelta, timezone

from services.mbh_service.auth import get_tpp_access_token
from shared.config.settings import settings

from services.mbh_service.token_manager import get_valid_account_access_token


def get_accounts():
    access_token = get_valid_account_access_token()

    response = requests.get(
        f"{settings.mbh_account_base_url}/accounts",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)



def create_account_access_consent():
    status, text, _headers = get_tpp_access_token()

    if status != 200:
        return status, text, {}

    access_token = json.loads(text)["access_token"]
    now = datetime.now(timezone.utc)

    payload = {
        "Data": {
            "Permissions": [
                "ReadAccountsBasic",
                "ReadAccountsDetail",
                "ReadBalances",
                "ReadTransactionsBasic",
                "ReadTransactionsCredits",
                "ReadTransactionsDebits",
                "ReadTransactionsDetail",
            ],
            "ExpirationDateTime": (now + timedelta(days=90)).isoformat().replace("+00:00", "Z"),
            "TransactionFromDateTime": (now - timedelta(days=90)).isoformat().replace("+00:00", "Z"),
            "TransactionToDateTime": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        },
        "Risk": {}
    }

    response = requests.post(
        f"{settings.mbh_account_base_url}/account-access-consents",
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json; charset=utf-8",
            "x-fapi-interaction-id": str(uuid.uuid4()),
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)


def get_transactions(account_id: str):
    access_token = get_valid_account_access_token()

    response = requests.get(
        f"{settings.mbh_account_base_url}/accounts/{account_id}/transactions",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)