def format_huf(value):
    if value is None or value == "":
        return "-"

    try:
        return f"{round(float(value)):,.0f}".replace(",", " ") + " Ft"
    except (ValueError, TypeError):
        return "-"


def format_vat(value):
    if value is None or value == "":
        return "-"

    try:
        vat = float(value)
    except (ValueError, TypeError):
        return "-"

    if vat == 0:
        return "K.ÁFA"

    return f"{round(vat * 100)}%"


def format_transaction_type(value):
    mapping = {
        "SALE": "ELADÁS",
        "PURCHASE": "VÉTEL",
        "SALE_STOCK_90_DAYS": "VÉTEL (90 NAP)",
    }

    return mapping.get(value, value or "-")