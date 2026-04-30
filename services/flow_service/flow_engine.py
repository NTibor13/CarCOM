from services.flow_service.flow_rules import is_sale_invoice_ready


def evaluate_transaction(tx: dict) -> dict:
    if is_sale_invoice_ready(tx):
        return {
            "action": "BILLINGO_DRAFT_REQUIRED",
            "reason": "Sale transaction ready for invoicing",
        }

    return {
        "action": None,
        "reason": None,
    }