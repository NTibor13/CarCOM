from services.flow_service.sales_flow_steps import (
    create_billingo_draft_step,
    convert_billingo_draft_to_invoice_step,
    download_document_step,
    upload_to_drive_step,
    update_sheet_status_step,
    update_sheet_link_step,
    generate_sales_preview_step,
)

from services.flow_service.purchase_flow_steps import (
    create_payment_batch_item_step,
    update_sheet_purchase_payment_status_step,
    create_billingo_spending_step,
)


SALE_FLOW_STEPS = [
    {
        "name": "CREATE_BILLINGO_DRAFT",
        "order": 10,
    },
    {
        "name": "GENERATE_SALES_PREVIEW",
        "order": 20,
    },

]

SALE_FINALIZE_FLOW_STEPS = [
    {
        "name": "CONVERT_BILLINGO_DRAFT_TO_INVOICE",
        "order": 10
    },
    {
        "name": "DOWNLOAD_DOCUMENT",
        "order": 20
    },
    {
        "name": "UPLOAD_TO_DRIVE",
        "order": 30
    },
    {
        "name": "UPDATE_SHEET_STATUS",
        "order": 40
    },
    {
        "name": "UPDATE_SHEET_LINK",
        "order": 50
    },
]

PURCHASE_FLOW_STEPS = [
    {
        "name": "CREATE_PAYMENT_BATCH_ITEM",
        "order": 10,
    },
    {
        "name": "CREATE_BILLINGO_SPENDING",
        "order": 20,
    },
    {
        "name": "UPDATE_SHEET_PURCHASE_PAYMENT_STATUS",
        "order": 30,
    },
]


def placeholder_step_handler(context: dict) -> dict:
    return {
        "message": "Placeholder step executed",
        "transaction_id": context.get("transaction_id"),
        "flow_type": context.get("flow_type"),
        "step_name": context.get("step_name"),
    }


STEP_HANDLERS = {
    "CREATE_BILLINGO_DRAFT": create_billingo_draft_step,
    "GENERATE_SALES_PREVIEW": generate_sales_preview_step,
    "CONVERT_BILLINGO_DRAFT_TO_INVOICE": convert_billingo_draft_to_invoice_step,
    "DOWNLOAD_DOCUMENT": download_document_step,
    "UPLOAD_TO_DRIVE": upload_to_drive_step,
    "UPDATE_SHEET_STATUS": update_sheet_status_step,
    "UPDATE_SHEET_LINK": update_sheet_link_step,
    "CREATE_PAYMENT_BATCH_ITEM": create_payment_batch_item_step,
    "CREATE_BILLINGO_SPENDING": create_billingo_spending_step,
    "UPDATE_SHEET_PURCHASE_PAYMENT_STATUS": update_sheet_purchase_payment_status_step,
}
