def is_sale_invoice_ready(tx: dict) -> bool:
    if tx["transaction_type"] != "SALE":
        return False

    if tx["normalized_status"] != "VALID":
        return False

    if tx["source_cost_center"] not in ("Eladás", "Eladás készlet 90 nap"):
        return False

    partner = (tx["partner_name"] or "").strip().lower().replace(".", "")
    if partner != "kocsiguru kft":
        return False

    if tx["invoice_status"] != "Számlára vár":
        return False

    required_fields = [
        tx["transaction_date"],
        tx["source_account"],
        tx["gross_amount_huf"],
        tx["vat_rate"],
        tx["net_amount_huf"],
        tx["car_name"],
    ]

    return all(v not in (None, "") for v in required_fields)