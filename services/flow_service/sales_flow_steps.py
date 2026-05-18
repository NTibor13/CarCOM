import json
import time
from shared.database.connection import get_connection
from services.billingo_service.api_call_logger import log_api_call
from services.billingo_service.billingo_client import (
    BillingoApiError,
    create_draft_document,
    get_document,
    download_document,
    convert_draft_to_invoice,
    delete_document,
)
from services.billingo_service.billingo_payload_builder import build_billingo_payload
from services.billingo_service.invoice_link_repository import (
    create_invoice_link,
    get_active_invoice_link,
    mark_invoice_link_confirmed,
    mark_invoice_link_missing,
    mark_invoice_link_finalized,
    mark_invoice_link_superseded,
    mark_invoice_link_delete_failed,

)
from services.flow_service.flow_engine import evaluate_transaction

from pathlib import Path

from shared.config.settings import settings
from services.sync_service.google_drive_client import GoogleDriveClient
from services.billingo_service.invoice_completion_service import _build_invoice_file_name
from services.sync_service.google_sheets_client import GoogleSheetsClient
from services.preview_service.sales_invoice_preview import generate_sales_invoice_preview

def create_billingo_draft_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    transaction = _get_transaction(transaction_id)

    flow_result = evaluate_transaction(transaction)
    if flow_result["action"] != "SALES_READY":
        return {
            "status": "skipped",
            "reason": flow_result["reason"],
            "action": flow_result["action"],
        }

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
                "billingo_document_id": billingo_document_id,
                "billingo_document_number": active_link.get("billingo_document_number"),
                "invoice_link_id": active_link["id"],
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

        billingo_document_number = _extract_billingo_document_number(response)

        invoice_link_id = create_invoice_link(
            transaction_id=transaction_id,
            billingo_document_id=billingo_document_id,
            billingo_document_number=billingo_document_number,
            status="DRAFT_CREATED",
            api_log_id=api_log_id,
        )

        return {
            "status": "created",
            "billingo_document_id": billingo_document_id,
            "billingo_document_number": billingo_document_number,
            "invoice_link_id": invoice_link_id,
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


def _get_transaction(transaction_id: int) -> dict:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise RuntimeError(f"Transaction not found: {transaction_id}")

    return dict(row)


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


def download_document_step(
    transaction_id: int,
    flow_run_id: int,
    step_name: str = "DOWNLOAD_DOCUMENT",
) -> dict:
    _ = flow_run_id, step_name
    import time

    from services.billingo_service.billingo_client import (
        BillingoApiError,
        download_document,
    )

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        transaction = cur.fetchone()

        if transaction is None:
            raise ValueError(f"Transaction not found: {transaction_id}")

        transaction_id = dict(transaction)

        cur.execute(
            """
            SELECT *
            FROM billingo_invoice_links
            WHERE transaction_id = ?
              AND status = 'INVOICE_CREATED'
            ORDER BY id DESC
            LIMIT 1
            """,
            (transaction_id,),
        )
        active_link = cur.fetchone()

        if active_link is None:
            raise ValueError(
                f"No finalized Billingo invoice found for transaction_id={transaction_id}"
            )

        active_link = dict(active_link)

    billingo_document_id = active_link["billingo_document_id"]

    max_attempts = 5
    sleep_seconds = 3
    pdf_content = None
    last_error: BillingoApiError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            pdf_content = download_document(billingo_document_id)
            break

        except BillingoApiError as exc:
            last_error = exc

            log_api_call(
                provider="Billingo",
                endpoint=f"/documents/{billingo_document_id}/download",
                method="GET",
                transaction_id=transaction_id,
                request_payload={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                },
                response_status=exc.status_code,
                response_payload=exc.response_data,
                success=False,
                error_message=str(exc),
            )

            if exc.status_code != 202 or attempt == max_attempts:
                raise

            time.sleep(sleep_seconds)

    if pdf_content is None:
        raise last_error or RuntimeError("Billingo document download failed")

    tmp_dir = Path("data/tmp/invoices")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    file_name = _build_invoice_file_name(
        transaction=transaction,
        billingo_document_id=billingo_document_id,
        billingo_document_number=active_link["billingo_document_number"],
    )

    file_path = tmp_dir / file_name
    file_path.write_bytes(pdf_content)

    return {
        "status": "success",
        "reason": "billingo_invoice_pdf_downloaded",
        "transaction_id": transaction_id,
        "billingo_document_id": billingo_document_id,
        "file_name": file_name,
        "file_path": str(file_path),
        "attempts": attempt,
    }

def upload_to_drive_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    transaction = _get_transaction(transaction_id)

    active_link = get_active_invoice_link(transaction_id)
    if not active_link:
        raise RuntimeError(
            f"No active Billingo invoice link found for transaction: {transaction_id}"
        )

    billingo_document_id = int(active_link["billingo_document_id"])

    existing_billingo_upload = _get_existing_billingo_uploaded_document(
        transaction_id=transaction_id,
        billingo_document_id=billingo_document_id,
    )

    if existing_billingo_upload:
        return {
            "status": "already_uploaded",
            "document_id": existing_billingo_upload["id"],
            "billingo_document_id": billingo_document_id,
            "drive_file_id": existing_billingo_upload["raw_value"],
            "drive_link": existing_billingo_upload["file_url"],
            "file_name": existing_billingo_upload["file_name"],
        }

    file_name = _build_invoice_file_name(
        transaction=transaction,
        billingo_document_id=billingo_document_id,
        billingo_document_number=active_link.get("billingo_document_number"),
    )

    file_path = Path("data/tmp/invoices") / file_name

    if file_path.exists():
        pdf_content = file_path.read_bytes()
    else:
        pdf_content = download_document(billingo_document_id)

    drive_file = GoogleDriveClient().upload_pdf(
        file_name=file_name,
        content=pdf_content,
        folder_id=settings.billingo_invoice_drive_folder_id,
    )

    document_id = _create_invoice_document(
        transaction_id=transaction_id,
        file_name=file_name,
        file_url=drive_file["webViewLink"],
        raw_value=f"billingo_document_id:{billingo_document_id};drive_file_id:{drive_file['id']}",
        source_column="Billingo",
    )

    return {
        "status": "uploaded",
        "document_id": document_id,
        "billingo_document_id": billingo_document_id,
        "drive_file_id": drive_file["id"],
        "drive_link": drive_file["webViewLink"],
        "file_name": file_name,
    }


def _get_existing_billingo_uploaded_document(
        transaction_id: int,
        billingo_document_id: int,
) -> dict | None:
    expected_raw_value_prefix = f"billingo_document_id:{billingo_document_id};"

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM finance_transaction_documents
            WHERE transaction_id = ?
              AND document_type = 'INVOICE'
              AND source_column = 'Billingo'
              AND raw_value LIKE ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                transaction_id,
                expected_raw_value_prefix + "%",
            ),
        )
        row = cur.fetchone()

    return dict(row) if row else None


def _get_existing_invoice_document(transaction_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM finance_transaction_documents
            WHERE transaction_id = ?
              AND document_type = ?
              AND source_column = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (
                transaction_id,
                "INVOICE",
                "Számla link",
            ),
        )
        row = cur.fetchone()

    return dict(row) if row else None


def _create_invoice_document(
        transaction_id: int,
        file_name: str,
        file_url: str,
        raw_value: str,
        source_column: str = "Számla link",
) -> int:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO finance_transaction_documents (
                transaction_id,
                document_type,
                source_column,
                file_name,
                file_url,
                raw_value,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                transaction_id,
                "INVOICE",
                source_column,
                file_name,
                file_url,
                raw_value,
            ),
        )

        document_id = cur.lastrowid
        conn.commit()

    return document_id


def update_sheet_status_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    transaction = _get_transaction(transaction_id)

    target_invoice_status = "Számlázott"
    target_payment_status = "Kiegyenlítésre vár (eladás)"

    if (
            transaction.get("invoice_status") == target_invoice_status
            and transaction.get("payment_status") == target_payment_status
    ):
        return {
            "status": "already_updated",
            "invoice_status": target_invoice_status,
            "payment_status": target_payment_status,
        }

    row_number = int(transaction["source_row_number"])

    GoogleSheetsClient().update_row_values(
        row_number=row_number,
        values_by_header={
            "Státusz Számla": target_invoice_status,
            "Státusz fizetés": target_payment_status,
        },
    )

    _update_local_transaction_status(
        transaction_id=transaction_id,
        invoice_status=target_invoice_status,
        payment_status=target_payment_status,
    )

    return {
        "status": "updated",
        "row_number": row_number,
        "invoice_status": target_invoice_status,
        "payment_status": target_payment_status,
    }


def _update_local_transaction_status(
        transaction_id: int,
        invoice_status: str,
        payment_status: str,
) -> None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE finance_transactions
            SET invoice_status = ?,
                payment_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                invoice_status,
                payment_status,
                transaction_id,
            ),
        )
        conn.commit()


def update_sheet_link_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    flow_run_id = int(context["flow_run_id"])
    transaction = _get_transaction(transaction_id)

    uploaded_invoice = _get_upload_to_drive_output(flow_run_id)

    if not uploaded_invoice:
        raise Exception(
            f"No uploaded invoice document found in UPLOAD_TO_DRIVE output for transaction: {transaction_id}"
        )

    drive_link = uploaded_invoice.get("drive_link")
    drive_file_id = uploaded_invoice.get("drive_file_id")

    if not drive_file_id and drive_link:
        drive_file_id = drive_link.split("/file/d/")[1].split("/")[0]

    if not drive_link:
        raise Exception(
            f"UPLOAD_TO_DRIVE output does not contain drive_link for transaction: {transaction_id}. "
            f"UPLOAD_TO_DRIVE output: {uploaded_invoice}"
        )

    if not drive_file_id:
        raise Exception(
            f"UPLOAD_TO_DRIVE output does not contain drive_file_id for transaction: {transaction_id}. "
            f"UPLOAD_TO_DRIVE output: {uploaded_invoice}"
        )

    row_number = int(transaction["source_row_number"])

    existing_file_ids = _get_existing_document_file_ids(transaction_id)

    all_file_ids = existing_file_ids + [drive_file_id]

    print("DEBUG uploaded_invoice:", uploaded_invoice)
    print("DEBUG existing_file_ids:", existing_file_ids)
    print("DEBUG drive_file_id:", drive_file_id)
    print("DEBUG all_file_ids:", all_file_ids)

    GoogleSheetsClient().update_drive_file_chips(
        row_number=row_number,
        header_name="Számla link",
        file_ids=all_file_ids,
    )

    return {
        "status": "updated",
        "row_number": row_number,
        "document_id": uploaded_invoice.get("document_id"),
        "drive_file_id": drive_file_id,
        "drive_link": drive_link,
        "header_name": "Számla link",
    }


def _get_upload_to_drive_output(flow_run_id: int) -> dict | None:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT output_json
            FROM flow_step_logs
            WHERE flow_run_id = ?
              AND step_name = 'UPLOAD_TO_DRIVE'
              AND status = 'SUCCESS'
              AND output_json IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (flow_run_id,),
        )
        row = cur.fetchone()

    if not row or not row["output_json"]:
        return None

    return json.loads(row["output_json"])


def _get_existing_document_file_ids(transaction_id: int) -> list[str]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT file_url
            FROM finance_transaction_documents
            WHERE transaction_id = ?
              AND source_column = ?
              AND file_url IS NOT NULL
              AND TRIM(file_url) != ''
            ORDER BY id ASC
            """,
            (
                transaction_id,
                "Számla link",
            ),
        )
        rows = cur.fetchall()

    file_ids = []

    for row in rows:
        file_url = row["file_url"]

        if "/file/d/" in file_url:
            file_id = file_url.split("/file/d/")[1].split("/")[0]
        elif "id=" in file_url:
            file_id = file_url.split("id=")[1].split("&")[0]
        else:
            continue

        if file_id and file_id not in file_ids:
            file_ids.append(file_id)

    return file_ids


def convert_billingo_draft_to_invoice_step(context: dict) -> dict:
    transaction_id = int(context["transaction_id"])
    active_link = get_active_invoice_link(transaction_id)

    if not active_link:
        raise RuntimeError(f"No active Billingo draft found for transaction: {transaction_id}")

    if active_link.get("status") == "INVOICE_CREATED":
        return {
            "status": "already_finalized",
            "billingo_document_id": active_link["billingo_document_id"],
            "billingo_document_number": active_link.get("billingo_document_number"),
            "invoice_link_id": active_link["id"],
        }

    billingo_document_id = int(active_link["billingo_document_id"])

    transaction = context.get("transaction")
    if transaction is None:
        transaction = _get_transaction(transaction_id)

    payload = build_billingo_payload(
        transaction,
        document_type="invoice",
    )

    try:
        response = convert_draft_to_invoice(
            billingo_document_id,
            payload,
        )

        api_log_id = log_api_call(
            provider="Billingo",
            endpoint=f"/documents/{billingo_document_id}",
            method="PUT",
            transaction_id=transaction_id,
            request_payload=payload,
            response_status=200,
            response_payload=response,
            success=True,
        )

        billingo_document_number = _extract_billingo_document_number(response)

        mark_invoice_link_finalized(
            link_id=active_link["id"],
            billingo_document_number=billingo_document_number,
            api_log_id=api_log_id,
        )

        return {
            "status": "finalized",
            "billingo_document_id": billingo_document_id,
            "billingo_document_number": billingo_document_number,
            "invoice_link_id": active_link["id"],
            "api_log_id": api_log_id,
        }

    except BillingoApiError as exc:
        log_api_call(
            provider="Billingo",
            endpoint=f"/documents/{billingo_document_id}",
            method="PUT",
            transaction_id=transaction_id,
            request_payload=payload,
            response_status=exc.status_code,
            response_payload=exc.response_data,
            success=False,
            error_message=str(exc),
        )
        raise

def supersede_existing_draft_for_restart(transaction_id: int) -> dict:
    active_link = get_active_invoice_link(transaction_id)

    if not active_link:
        return {
            "status": "no_active_link",
            "reason": "No active Billingo draft or invoice link found.",
        }

    link_status = active_link.get("status")
    billingo_document_id = int(active_link["billingo_document_id"])

    if link_status == "INVOICE_CREATED":
        return {
            "status": "invoice_kept",
            "reason": "Existing finalized invoice is kept. New flow can create a new draft.",
            "billingo_document_id": billingo_document_id,
            "invoice_link_id": active_link["id"],
        }

    try:
        response = delete_document(billingo_document_id)

        api_log_id = log_api_call(
            provider="Billingo",
            endpoint=f"/documents/{billingo_document_id}",
            method="DELETE",
            transaction_id=transaction_id,
            request_payload=None,
            response_status=204,
            response_payload=response,
            success=True,
        )

        mark_invoice_link_superseded(active_link["id"], api_log_id)

        return {
            "status": "draft_deleted_and_superseded",
            "billingo_document_id": billingo_document_id,
            "invoice_link_id": active_link["id"],
            "api_log_id": api_log_id,
        }

    except BillingoApiError as exc:
        api_log_id = log_api_call(
            provider="Billingo",
            endpoint=f"/documents/{billingo_document_id}",
            method="DELETE",
            transaction_id=transaction_id,
            request_payload=None,
            response_status=exc.status_code,
            response_payload=exc.response_data,
            success=False,
            error_message=str(exc),
        )

        if exc.status_code in (404, 410):
            mark_invoice_link_superseded(active_link["id"], api_log_id)
            return {
                "status": "draft_missing_but_superseded",
                "billingo_document_id": billingo_document_id,
                "invoice_link_id": active_link["id"],
                "api_log_id": api_log_id,
            }

        mark_invoice_link_delete_failed(active_link["id"], api_log_id)
        raise

def generate_sales_preview_step(context: dict) -> dict:
    transaction = context.get("transaction")

    if transaction is None:
        transaction_id = int(context["transaction_id"])

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM finance_transactions WHERE id = ?",
                (transaction_id,),
            )
            row = cur.fetchone()

        if row is None:
            raise RuntimeError(f"Transaction not found: {transaction_id}")

        transaction = dict(row)

    preview_path = generate_sales_invoice_preview(transaction)

    return {
        "status": "success",
        "preview_path": str(preview_path),
    }