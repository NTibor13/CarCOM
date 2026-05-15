from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

from shared.database.connection import get_connection


EXPORT_DIR = Path("data/payment_exports")
ENCODING = "iso-8859-2"


def export_batch_to_mbh_huf_xml_101(
    batch_id: int,
    debtor_account: str,
    debtor_name: str = "NF Office Kft.",
) -> dict:
    batch = _load_batch(batch_id)
    if not batch:
        raise RuntimeError(f"Payment batch not found: {batch_id}")

    items = _load_batch_items(batch_id)
    if not items:
        raise RuntimeError(f"Payment batch has no items: {batch_id}")

    value_date = date.today().strftime("%Y-%m-%d")
    debtor_account = _normalize_bank_account(debtor_account)

    root = ET.Element("HUFTransactions")

    for item in items:
        transaction = ET.SubElement(root, "Transaction")

        reference = str(item.get("transaction_id") or item.get("id") or "")[:6]
        if reference:
            ET.SubElement(transaction, "CustomerSpecifiedReference").text = reference

        originator = ET.SubElement(transaction, "Originator")
        originator_account = ET.SubElement(originator, "Account")
        ET.SubElement(originator_account, "AccountNumber").text = debtor_account
        ET.SubElement(originator_account, "Name").text = _safe_text(debtor_name, 70)

        beneficiary = ET.SubElement(transaction, "Beneficiary")
        beneficiary_account = ET.SubElement(beneficiary, "Account")
        ET.SubElement(beneficiary_account, "AccountNumber").text = _normalize_bank_account(
            item["creditor_bank_account"]
        )
        ET.SubElement(beneficiary_account, "Name").text = _safe_text(
            item["creditor_name"], 70
        )

        ET.SubElement(transaction, "RequestedExecutionDate").text = value_date

        amount = ET.SubElement(transaction, "Amount", {"Currency": "HUF"})
        amount.text = _format_amount(item["amount_huf"])

        text1, text2, text3 = _split_remittance(item.get("payment_notice") or "")

        remittance = ET.SubElement(transaction, "RemittanceInfo")
        if text1:
            ET.SubElement(remittance, "Text1").text = text1
        if text2:
            ET.SubElement(remittance, "Text2").text = text2
        if text3:
            ET.SubElement(remittance, "Text3").text = text3

    xml_bytes = _to_pretty_xml_bytes(root)

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    file_name = f"FA_CARCOM_{batch_id}_{date.today().strftime('%Y%m%d')}.XML"
    file_path = EXPORT_DIR / file_name
    file_path.write_bytes(xml_bytes)

    _mark_batch_exported(batch_id=batch_id, file_name=file_name, file_path=str(file_path))

    return {
        "status": "success",
        "payment_batch_id": batch_id,
        "format": "MBH_HUF_XML_101",
        "file_name": file_name,
        "file_path": str(file_path),
        "item_count": len(items),
        "encoding": ENCODING,
        "value_date": value_date,
    }


def _to_pretty_xml_bytes(root: ET.Element) -> bytes:
    rough = ET.tostring(root, encoding=ENCODING, xml_declaration=True)
    parsed = minidom.parseString(rough)
    pretty = parsed.toprettyxml(indent="  ", encoding=ENCODING)
    return pretty


def _normalize_bank_account(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")

    if len(digits) not in (16, 24):
        raise RuntimeError(f"Invalid Hungarian bank account number: {value}")

    return digits.ljust(24, "0")


def _format_amount(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if amount <= 0:
        raise RuntimeError(f"Invalid payment amount: {value}")

    return str(int(amount))


def _safe_text(value: str, max_length: int) -> str:
    text = str(value or "").strip()

    if not text:
        raise RuntimeError("Required text value is missing")

    encoded = text.encode(ENCODING, errors="replace")

    while len(encoded) > max_length:
        text = text[:-1]
        encoded = text.encode(ENCODING, errors="replace")

    return text


def _split_remittance(value: str) -> tuple[str, str, str]:
    text = str(value or "").strip()
    encoded_text = text.encode(ENCODING, errors="replace").decode(ENCODING)

    chunks = []
    remaining = encoded_text

    for _ in range(3):
        chunk = remaining[:32]
        chunks.append(chunk)
        remaining = remaining[32:]

    while len(chunks) < 3:
        chunks.append("")

    return chunks[0], chunks[1], chunks[2]


def _load_batch(batch_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM payment_batches WHERE id = ?", (batch_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def _load_batch_items(batch_id: int) -> list[dict]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM payment_batch_items
            WHERE batch_id = ?
            ORDER BY id
            """,
            (batch_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def _mark_batch_exported(batch_id: int, file_name: str, file_path: str) -> None:
    with get_connection() as conn:
        cur = conn.cursor()

        _ensure_export_columns(cur)

        cur.execute(
            """
            UPDATE payment_batches
            SET
                status = 'EXPORTED',
                export_format = 'MBH_HUF_XML_101',
                export_file_name = ?,
                export_file_path = ?,
                exported_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_name, file_path, batch_id),
        )

        conn.commit()


def _ensure_export_columns(cur) -> None:
    cur.execute("PRAGMA table_info(payment_batches)")
    existing = {row["name"] for row in cur.fetchall()}

    columns = {
        "export_format": "TEXT",
        "export_file_name": "TEXT",
        "export_file_path": "TEXT",
        "exported_at": "TEXT",
    }

    for name, column_type in columns.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE payment_batches ADD COLUMN {name} {column_type}")