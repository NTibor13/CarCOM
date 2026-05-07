from services.flow_service.flow_rules import (
    is_purchase_payment_ready,
    is_sale_invoice_ready,
)


def evaluate_transaction(tx: dict) -> dict:
    if is_sale_invoice_ready(tx):
        return {
            "action": "SALES_READY",
            "reason": "Sale transaction ready for invoicing",
        }

    if is_purchase_payment_ready(tx):
        return {
            "action": "PURCHASE_PAYMENT_READY",
            "reason": "Purchase transaction ready for payment preparation",
        }

    return {
        "action": None,
        "reason": None,
    }