from services.flow_service.steps_billingo import create_billingo_draft_step

SALE_FLOW_STEPS = [
    {
        "name": "CREATE_BILLINGO_DRAFT",
        "order": 10,
    },
    {
        "name": "DOWNLOAD_DOCUMENT",
        "order": 20,
    },
    {
        "name": "UPLOAD_TO_DRIVE",
        "order": 30,
    },
    {
        "name": "UPDATE_SHEET_STATUS",
        "order": 40,
    },
    {
        "name": "UPDATE_SHEET_LINK",
        "order": 50,
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
    "DOWNLOAD_DOCUMENT": placeholder_step_handler,
    "UPLOAD_TO_DRIVE": placeholder_step_handler,
    "UPDATE_SHEET_STATUS": placeholder_step_handler,
    "UPDATE_SHEET_LINK": placeholder_step_handler,
}