import json
import uuid

import requests

from shared.config.settings import settings
from services.mbh_service.auth import (
    build_payment_jws_signature,
    get_payment_tpp_access_token,
)


def create_domestic_payment_consent(
    *,
    amount: str,
    currency: str,
    creditor_name: str,
    creditor_scheme_name: str,
    creditor_identification: str,
    reference: str | None = None,
):
    status, text, _headers = get_payment_tpp_access_token()

    if status != 200:
        return status, text, {}

    access_token = json.loads(text)["access_token"]

    instruction_id = f"CARCOM-{uuid.uuid4().hex[:20]}"[:35]

    initiation = {
        "InstructionIdentification": instruction_id,
        "EndToEndIdentification": instruction_id,
        "InstructedAmount": {
            "Amount": amount,
            "Currency": currency,
        },
        "CreditorAccount": {
            "SchemeName": creditor_scheme_name,
            "Identification": creditor_identification,
            "Name": creditor_name,
        },
    }

    if reference:
        initiation["RemittanceInformation"] = {
            "Reference": reference[:35],
            "Unstructured": reference[:140],
        }

    payload = {
        "Data": {
            "Initiation": initiation,
        },
        "Risk": {},
    }

    jws_signature = build_payment_jws_signature(payload=payload)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    response = requests.post(
        f"{settings.mbh_payment_base_url}/domestic-payment-consents",
        data=payload_json.encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json; charset=utf-8",
            "x-idempotency-key": uuid.uuid4().hex[:40],
            "x-jws-signature": jws_signature,
        },
        timeout=30,
    )

    return response.status_code, response.text, dict(response.headers)
