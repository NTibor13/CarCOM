import base64
import hashlib
import json
import time
import uuid
from urllib.parse import urlencode

import jwt
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from shared.config.settings import settings

from services.mbh_service.certificates import (
    get_mbh_signing_issuer,
    load_mbh_signing_private_key_pem,
    load_mbh_signing_public_key_pem,
)


CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def _load_private_key() -> str:
    return load_mbh_signing_private_key_pem()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def build_client_assertion(client_id: str) -> str:
    now = int(time.time())
    private_key = _load_private_key()

    payload = {
        "iss": client_id,
        "sub": client_id,
        "aud": settings.mbh_token_url,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 60,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


def get_tpp_access_token_for_scope(*, client_id: str, scope: str):
    client_assertion = build_client_assertion(client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "scope": scope,
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


def get_tpp_access_token():
    return get_tpp_access_token_for_scope(
        client_id=settings.mbh_account_client_id,
        scope="accounts",
    )


def get_payment_tpp_access_token():
    return get_tpp_access_token_for_scope(
        client_id=settings.mbh_payment_client_id,
        scope="payments",
    )


def build_authorization_request_object(
    *,
    consent_id: str,
    nonce: str,
    client_id: str,
    scope: str,
) -> str:
    now = int(time.time())
    private_key = _load_private_key()

    payload = {
        "iss": client_id,
        "aud": settings.mbh_issuer_url,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": settings.mbh_redirect_uri,
        "scope": f"openid {scope}",
        "state": str(uuid.uuid4()),
        "nonce": nonce,
        "claims": {
            "userinfo": {
                "openbanking_intent_id": {
                    "value": consent_id,
                }
            },
            "id_token": {
                "openbanking_intent_id": {
                    "value": consent_id,
                }
            },
        },
        "iat": now,
        "exp": now + 60,
    }

    return jwt.encode(payload, private_key, algorithm="RS256")


def build_authorization_url_for_scope(
    *,
    consent_id: str,
    client_id: str,
    scope: str,
) -> str:
    state = str(uuid.uuid4())
    nonce = str(uuid.uuid4())

    request_object = build_authorization_request_object(
        consent_id=consent_id,
        nonce=nonce,
        client_id=client_id,
        scope=scope,
    )

    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": f"openid {scope}",
        "redirect_uri": settings.mbh_redirect_uri,
        "state": state,
        "nonce": nonce,
        "request": request_object,
    }

    return f"{settings.mbh_authorization_url}?{urlencode(params)}"


def build_authorization_url(consent_id: str) -> str:
    return build_authorization_url_for_scope(
        consent_id=consent_id,
        client_id=settings.mbh_account_client_id,
        scope="accounts",
    )


def build_payment_authorization_url(consent_id: str) -> str:
    return build_authorization_url_for_scope(
        consent_id=consent_id,
        client_id=settings.mbh_payment_client_id,
        scope="payments",
    )


def exchange_authorization_code_for_scope(
    *,
    code: str,
    client_id: str,
):
    client_assertion = build_client_assertion(client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
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


def exchange_authorization_code(code: str):
    return exchange_authorization_code_for_scope(
        code=code,
        client_id=settings.mbh_account_client_id,
    )


def exchange_payment_authorization_code(code: str):
    return exchange_authorization_code_for_scope(
        code=code,
        client_id=settings.mbh_payment_client_id,
    )


def refresh_psu_access_token_for_client(
    *,
    refresh_token: str,
    client_id: str,
):
    client_assertion = build_client_assertion(client_id)

    response = requests.post(
        settings.mbh_token_url,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
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


def refresh_psu_access_token(refresh_token: str):
    return refresh_psu_access_token_for_client(
        refresh_token=refresh_token,
        client_id=settings.mbh_account_client_id,
    )


def refresh_payment_psu_access_token(refresh_token: str):
    return refresh_psu_access_token_for_client(
        refresh_token=refresh_token,
        client_id=settings.mbh_payment_client_id,
    )


def generate_public_key_thumbprint(public_key_pem: str) -> str:
    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))

    if not isinstance(public_key, rsa.RSAPublicKey):
        raise ValueError("RSA public key required")

    numbers = public_key.public_numbers()
    exponent = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
    modulus = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")

    jwk = {
        "e": _b64url(exponent),
        "kty": "RSA",
        "n": _b64url(modulus),
    }

    jwk_json = json.dumps(jwk, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(jwk_json.encode("utf-8")).digest()

    return _b64url(digest)


def get_payment_signing_key_id() -> str:
    return generate_public_key_thumbprint(load_mbh_signing_public_key_pem())


def build_payment_jws_signature(*, payload: dict) -> str:
    private_key = serialization.load_pem_private_key(
        _load_private_key().encode("utf-8"),
        password=None,
    )

    header = {
        "alg": "RS256",
        "kid": get_payment_signing_key_id(),
        "b64": False,
        "http://openbanking.org.uk/iat": int(time.time()) - 60,
        "http://openbanking.org.uk/iss": get_mbh_signing_issuer(),
        "crit": [
            "b64",
            "http://openbanking.org.uk/iat",
            "http://openbanking.org.uk/iss",
        ],
    }

    header_json = json.dumps(header, separators=(",", ":"), ensure_ascii=False)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    encoded_header = _b64url(header_json.encode("utf-8"))
    encoded_payload = _b64url(payload_json.encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")

    signature = private_key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    return f"{encoded_header}..{_b64url(signature)}"
