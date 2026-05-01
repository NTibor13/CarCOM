from services.billingo_service.api_call_logger import log_api_call
from services.billingo_service.billingo_client import (
    BillingoApiError,
    create_draft_document,
    get_document,
)
from services.billingo_service.billingo_payload_builder import build_billingo_payload
from services.billingo_service.invoice_link_repository import (
    create_invoice_link,
    get_active_invoice_link,
    mark_invoice_link_confirmed,
    mark_invoice_link_missing,
)


def _extract_billingo_document_id(response: dict) -> int | None:
    value = response.get("id") or response.get("document_id")
    return int(value) if value is not None else None


def _extract_billingo_document_number(response: dict) -> str | None:
    value = (
        response.get("invoice_number")
        or response.get("document_number")
        or response.get("number")
    )
    return str(value) if value is not None else None


def ensure_billingo_draft_for_transaction(transaction: dict) -> dict:
    transaction_id = int(transaction["id"])

    active_link = get_active_invoice_link(transaction_id)

    if active_link:
        billingo_document_id = int(active_link["billingo_document_id"])

        try:
            response = get_document(billingo_document_id)

            api_log_id = log_api_call(
                provider="Billingo",
                endpoint=f"/documents/{billingo_document_id}",
                method="GET",
                transaction_id=transaction_id,
                request_payload=None,
                response_status=200,
                response_payload=response,
                success=True,
            )

            mark_invoice_link_confirmed(active_link["id"], api_log_id)

            return {
                "status": "already_exists",
                "invoice_link": active_link,
                "billingo_response": response,
            }

        except BillingoApiError as exc:
            api_log_id = log_api_call(
                provider="Billingo",
                endpoint=f"/documents/{billingo_document_id}",
                method="GET",
                transaction_id=transaction_id,
                request_payload=None,
                response_status=exc.status_code,
                response_payload=exc.response_data,
                success=False,
                error_message=str(exc),
            )

            error_message = ""
            if isinstance(exc.response_data, dict):
                error_message = (
                        exc.response_data.get("error", {}).get("message")
                        or exc.response_data.get("message")
                        or ""
                )

            is_missing_document_error = (
                    exc.status_code == 404
                    or (
                            exc.status_code == 403
                            and "invalid" in error_message.lower()
                    )
            )

            if is_missing_document_error:
                mark_invoice_link_missing(active_link["id"], api_log_id)
            else:
                raise

    payload = build_billingo_payload(transaction)

    try:
        response = create_draft_document(payload)

        api_log_id = log_api_call(
            provider="Billingo",
            endpoint="/documents",
            method="POST",
            transaction_id=transaction_id,
            request_payload=payload,
            response_status=201,
            response_payload=response,
            success=True,
        )

        billingo_document_id = _extract_billingo_document_id(response)

        if billingo_document_id is None:
            raise BillingoApiError(
                "Billingo response does not contain document id",
                status_code=201,
                response_data=response,
            )

        create_invoice_link(
            transaction_id=transaction_id,
            billingo_document_id=billingo_document_id,
            billingo_document_number=_extract_billingo_document_number(response),
            status="DRAFT_CREATED",
            api_log_id=api_log_id,
        )

        return {
            "status": "created",
            "billingo_response": response,
        }

    except BillingoApiError as exc:
        log_api_call(
            provider="Billingo",
            endpoint="/documents",
            method="POST",
            transaction_id=transaction_id,
            request_payload=payload,
            response_status=exc.status_code,
            response_payload=exc.response_data,
            success=False,
            error_message=str(exc),
        )
        raise