from shared.config.settings import settings
from shared.database.connection import get_connection
from services.billingo_service.billingo_client import download_document
from services.sync_service.google_drive_client import GoogleDriveClient
from services.sync_service.google_sheets_client import GoogleSheetsClient


def complete_invoice_process(
    transaction: dict,
    billingo_document_id: int,
    billingo_document_number: str | None,
) -> dict:
    pdf_content = download_document(billingo_document_id)

    file_name = _build_invoice_file_name(
        transaction=transaction,
        billingo_document_id=billingo_document_id,
        billingo_document_number=billingo_document_number,
    )

    drive_file = GoogleDriveClient().upload_pdf(
        file_name=file_name,
        content=pdf_content,
        folder_id=settings.billingo_invoice_drive_folder_id,
    )

    drive_link = drive_file["webViewLink"]
    drive_file_id = drive_file["id"]

    sheets_client = GoogleSheetsClient()

    sheets_client.update_row_values(
        row_number=int(transaction["source_row_number"]),
        values_by_header={
            "Státusz Számla": "Számlázott",
            "Státusz fizetés": "Kiegyenlítésre vár (eladás)",
        },
    )

    sheets_client.update_drive_file_chip(
        row_number=int(transaction["source_row_number"]),
        header_name="Számla link",
        file_id=drive_file_id,
        display_text="Számla",
    )

    _update_local_transaction_status(
        transaction_id=int(transaction["id"]),
        invoice_status="Számlázott",
        payment_status="Kiegyenlítésre vár (eladás)",
    )

    return {
        "drive_file_id": drive_file["id"],
        "drive_link": drive_link,
        "file_name": file_name,
    }


def _build_invoice_file_name(
    transaction: dict,
    billingo_document_id: int,
    billingo_document_number: str | None,
) -> str:
    source_row_number = transaction.get("source_row_number")
    car_name = transaction.get("car_name") or "auto"
    partner_name = transaction.get("partner_name") or "partner"
    document_number = billingo_document_number or str(billingo_document_id)

    safe_name = f"{source_row_number}_{document_number}_{car_name}"
    safe_name = (
        safe_name
        .replace("/", "-")
        .replace("\\", "-")
        .replace(":", "-")
        .replace("*", "-")
        .replace("?", "")
        .replace('"', "")
        .replace("<", "")
        .replace(">", "")
        .replace("|", "")
        .strip()
        .rstrip(". ")
    )

    return f"{safe_name}.pdf"


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
            (invoice_status, payment_status, transaction_id),
        )
        conn.commit()