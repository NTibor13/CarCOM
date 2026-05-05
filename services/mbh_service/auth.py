import time
import uuid
import jwt
import requests
from shared.config.settings import settings
from urllib.parse import urlencode

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

def build_authorization_request_object(consent_id: str, nonce: str) -> str:
    now = int(time.time())

    with open(settings.mbh_private_key_path, "r", encoding="utf-8") as key_file:
        private_key = key_file.read()

    payload = {
        "iss": settings.mbh_account_client_id,
        "aud": settings.mbh_issuer_url,
        "response_type": "code",
        "client_id": settings.mbh_account_client_id,
        "redirect_uri": settings.mbh_redirect_uri,
        "scope": "openid accounts",
        "state": str(uuid.uuid4()),
        "nonce": nonce,
        "claims": {
            "userinfo": {
                "openbanking_intent_id": {
                    "value": consent_id
                }
            },
            "id_token": {
                "openbanking_intent_id": {
                    "value": consent_id
                }
            }
        },
        "iat": now,
        "exp": now + 300,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")

def build_authorization_url(consent_id: str) -> str:
    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())

    request_object = build_authorization_request_object(consent_id, nonce)

    params = {
        "client_id": settings.mbh_account_client_id,
        "response_type": "code",
        "scope": "openid accounts",
        "redirect_uri": settings.mbh_redirect_uri,
        "state": state,
        "nonce": nonce,
        "request": request_object,
    }

    return f"{settings.mbh_authorization_url}?{urlencode(params)}"

def exchange_authorization_code(code: str):
    client_assertion = build_client_assertion(settings.mbh_account_client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.mbh_account_client_id,
            "code": code,
            "redirect_uri": settings.mbh_redirect_uri,
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": client_assertion,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)

def build_client_assertion(client_id: str) -> str:
    now = int(time.time())

    with open(settings.mbh_private_key_path, "r", encoding="utf-8") as key_file:
        private_key = key_file.read()

    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": settings.mbh_token_url,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 300,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")

def get_tpp_access_token():
    client_assertion = build_client_assertion(settings.mbh_account_client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": settings.mbh_account_client_id,
            "scope": "accounts",
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": client_assertion,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)

def refresh_psu_access_token(refresh_token: str):
    client_assertion = build_client_assertion(settings.mbh_account_client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.mbh_account_client_id,
            "refresh_token": refresh_token,
            "client_assertion_type": CLIENT_ASSERTION_TYPE,
            "client_assertion": client_assertion,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)