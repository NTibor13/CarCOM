import os
import requests
from dotenv import load_dotenv


load_dotenv()


class BillingoApiError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


def create_draft_document(payload: dict) -> dict:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents"

    response = requests.post(
        url,
        json=payload,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code not in (200, 201):
        raise BillingoApiError(
            f"Billingo API error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response_data

def get_document(document_id: int) -> dict:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}"

    response = requests.get(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
        },
        timeout=30,
    )

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code != 200:
        raise BillingoApiError(
            f"Billingo API error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response_data

def download_document(document_id: int) -> bytes:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}/download"

    response = requests.get(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/pdf",
        },
        timeout=30,
    )

    if response.status_code != 200:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_response": response.text}

        raise BillingoApiError(
            f"Billingo document download error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response.content


def _download_document_pdf(document_id: int) -> bytes:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}/download"

    response = requests.get(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/pdf",
        },
        timeout=30,
    )

    if response.status_code != 200:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_response": response.text}

        raise BillingoApiError(
            f"Billingo document download error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response.content


def print_pos_document(document_id: int) -> bytes:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}/print/pos"

    response = requests.get(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/pdf",
        },
        timeout=30,
    )

    if response.status_code != 200:
        try:
            response_data = response.json()
        except ValueError:
            response_data = {"raw_response": response.text}

        raise BillingoApiError(
            f"Billingo POS print error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response.content

def create_spending(payload: dict) -> dict:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/spendings"

    response = requests.post(
        url,
        json=payload,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=30,
    )

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code not in (200, 201):
        raise BillingoApiError(
            f"Billingo spending API error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response_data

def convert_draft_to_invoice(document_id: int, payload: dict) -> dict:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}"

    response = requests.put(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code not in (200, 201):
        raise BillingoApiError(
            f"Billingo draft convert API error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response_data


def delete_document(document_id: int) -> dict:
    api_key = os.getenv("BILLINGO_API_KEY")
    base_url = os.getenv("BILLINGO_API_BASE_URL", "https://api.billingo.hu/v3")

    if not api_key:
        raise BillingoApiError("Missing BILLINGO_API_KEY environment variable")

    url = f"{base_url}/documents/{document_id}"

    response = requests.delete(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
        },
        timeout=30,
    )

    try:
        response_data = response.json() if response.text else {}
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code not in (200, 204):
        raise BillingoApiError(
            f"Billingo document delete error {response.status_code}: {response_data}",
            status_code=response.status_code,
            response_data=response_data,
        )

    return response_data