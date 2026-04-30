def is_sale_invoice_ready(tx: dict) -> bool:
    if tx.get("transaction_type") != "SALE":
        return False

    if tx.get("normalized_status") != "VALID":
        return False

    if tx.get("source_cost_center") not in ("Eladás", "Eladás készlet 90 nap"):
        return False

    partner = (tx.get("partner_name") or "").strip().lower().replace(".", "")
    if partner != "kocsiguru kft":
        return False

    if tx.get("invoice_status") != "Számlára vár":
        return False

    required_fields = [
        tx.get("sheet_row_id"),
        tx.get("transaction_date"),
        tx.get("source_account"),
        tx.get("gross_amount_huf"),
        tx.get("vat_rate"),
        tx.get("net_amount_huf"),
        tx.get("car_name"),
    ]

    return all(v not in (None, "") for v in required_fields)