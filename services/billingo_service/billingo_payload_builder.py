from datetime import datetime, timedelta
from decimal import Decimal

def build_billingo_payload(tx: dict) -> dict:
    transaction_date = datetime.strptime(tx["transaction_date"], "%Y-%m-%d")

    # due date logika
    if tx["source_cost_center"] == "Eladás":
        due_date = transaction_date + timedelta(days=8)
    else:
        due_date = transaction_date + timedelta(days=90)

    # VAT mapping
    vat_rate = Decimal(str(tx.get("vat_rate") or "0"))

    if vat_rate == Decimal("0"):
        vat = "K.AFA"
    elif vat_rate == Decimal("0.27"):
        vat = "27%"
    else:
        vat = "27%"  # fallback

    # invoice comment
    invoice_comment = None
    if vat_rate == 0:
        invoice_comment = "Az ÁFA törvény 169§ alapján különbözet szerinti szabályozás – használt cikkek"

    payload = {
        "partner_id": 1851221817,
        "block_id": 156600,
        "bank_account_id": 0,
        "type": "draft",
        "fulfillment_date": transaction_date.strftime("%Y-%m-%d"),
        "due_date": due_date.strftime("%Y-%m-%d"),
        "payment_method": "wire_transfer",
        "language": "hu",
        "currency": "HUF",
        "electronic": True,
        "paid": False,
        "items": [
            {
                "name": "Gépjármű",
                "unit_price": int(Decimal(str(tx["net_amount_huf"])).quantize(Decimal("1"))),
                "unit_price_type": "net",
                "quantity": 1,
                "unit": "darab",
                "vat": vat,
                "comment": tx.get("car_name"),
                "entitlement": "SECOND_HAND",
            }
        ],
        "settings": {
            "round": "one",
            "should_send_email": True,
            "no_send_onlineszamla_by_user": False,
            "selected_type": "draft",
        },
    }

    if invoice_comment:
        payload["comment"] = invoice_comment

    return payload