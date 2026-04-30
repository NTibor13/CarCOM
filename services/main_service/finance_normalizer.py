import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from services.sync_service.google_sheets_client import GoogleSheetsClient

from shared.database.connection import get_connection
from services.main_service.finance_mapping import (
    DOCUMENT_COLUMNS,
    EXPECTED_FINANCE_HEADERS,
    INVOICE_STATUS_VALUES,
    KOLTSEGHELY_MAP,
    PAYMENT_STATUS_VALUES,
    SOURCE_ACCOUNT_VALUES,
    VAT_RATE_MAP,
)

SOURCE_NAME = "google_sheet_finance"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ValidationIssue:
    field_name: str
    error_code: str
    error_message: str
    severity: str = "ERROR"


@dataclass
class NormalizedTransaction:
    sheet_row_id: int
    source_row_number: int
    external_id: int | None
    transaction_date: str | None
    source_account: str
    gross_amount_huf: int | None
    vat_rate: str | None
    net_amount_huf: str | None
    source_cost_center: str
    transaction_type: str
    car_name: str
    partner_name: str
    bank_account: str
    payment_notice: str
    payment_deadline: str | None
    invoice_status: str
    payment_status: str
    kg_debt_huf: int | None
    note: str
    normalized_status: str
    issues: list[ValidationIssue] = field(default_factory=list)


class FinanceNormalizer:
    def normalize_active_rows(self) -> dict[str, int]:
        normalized = 0
        invalid = 0
        warnings = 0
        header_errors = 0

        document_links_by_cell = GoogleSheetsClient().read_document_links(
            list(DOCUMENT_COLUMNS.keys())
        )

        with get_connection() as conn:
            cur = conn.cursor()
            # A verzió: a normalizált köztes réteget minden futáskor újraépítjük.
            # Így a törölt/inaktív Google Sheet sorok nem maradnak bent szellemsorként.
            cur.execute("DELETE FROM finance_validation_errors")
            cur.execute("DELETE FROM finance_transaction_documents")
            cur.execute("DELETE FROM finance_transactions")
            cur.execute(
                """
                SELECT id, source_row_number, raw_json
                FROM sheet_rows_raw
                WHERE source_name = ? AND is_active = 1
                ORDER BY source_row_number
                """,
                (SOURCE_NAME,),
            )
            raw_rows = cur.fetchall()

            if raw_rows:
                header_errors = self._validate_headers(cur, json.loads(raw_rows[0]["raw_json"]).keys())

            for row in raw_rows:
                sheet_row_id = int(row["id"])
                source_row_number = int(row["source_row_number"])
                raw_data = json.loads(row["raw_json"])

                transaction = self._normalize_row(sheet_row_id, source_row_number, raw_data)
                transaction_id = self._upsert_transaction(cur, transaction)
                self._replace_documents(
                    cur,
                    transaction_id,
                    raw_data,
                    document_links_by_cell.get((source_row_number, None), []),
                    source_row_number,
                    document_links_by_cell,
                )
                self._replace_validation_issues(cur, transaction_id, sheet_row_id, transaction.issues)
                self._update_processing_flow_type(cur, sheet_row_id, transaction.transaction_type)

                normalized += 1
                if transaction.normalized_status == "INVALID":
                    invalid += 1
                elif transaction.normalized_status == "WARNING":
                    warnings += 1

            conn.commit()

        return {
            "normalized": normalized,
            "invalid": invalid,
            "warnings": warnings,
            "header_errors": header_errors,
        }

    def _validate_headers(self, cur, current_headers: Any) -> int:
        cur.execute("DELETE FROM source_header_validation WHERE source_name = ?", (SOURCE_NAME,))
        current = set(str(header).strip() for header in current_headers)
        expected = set(EXPECTED_FINANCE_HEADERS)
        error_count = 0
        timestamp = now_iso()

        for missing in sorted(expected - current):
            cur.execute(
                """
                INSERT INTO source_header_validation (
                    source_name, header_name, status, severity, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (SOURCE_NAME, missing, "MISSING", "ERROR", f"Hiányzó header: {missing}", timestamp),
            )
            error_count += 1

        for extra in sorted(current - expected):
            cur.execute(
                """
                INSERT INTO source_header_validation (
                    source_name, header_name, status, severity, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (SOURCE_NAME, extra, "EXTRA", "WARNING", f"Nem várt extra header: {extra}", timestamp),
            )

        if error_count == 0:
            cur.execute(
                """
                INSERT INTO source_header_validation (
                    source_name, header_name, status, severity, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (SOURCE_NAME, "*", "OK", "INFO", "A kötelező finance headerek rendben vannak", timestamp),
            )

        return error_count

    def _normalize_row(self, sheet_row_id: int, source_row_number: int, raw: dict[str, Any]) -> NormalizedTransaction:
        issues: list[ValidationIssue] = []

        external_id = self._parse_int(raw.get("ID", ""), "ID", issues, required=True)
        transaction_date = self._parse_date(raw.get("Datum", ""), "Datum", issues, required=True)
        source_account = self._text(raw.get("Számla", ""))
        gross_amount_huf = self._parse_money_int(raw.get("Osszeg (brutto)", ""), "Osszeg (brutto)", issues,
                                                 required=True, absolute=True)
        vat_rate = self._parse_vat_rate(raw.get("Afa %", ""), issues)
        net_amount_huf = self._calculate_net_amount(gross_amount_huf, vat_rate)
        source_net = self._parse_money_decimal(raw.get("Osszeg (netto)", ""), "Osszeg (netto)", issues, required=False,
                                               absolute=True)
        source_cost_center = self._text(raw.get("Koltseghely", ""))
        transaction_type = KOLTSEGHELY_MAP.get(source_cost_center, "UNKNOWN")
        car_name = self._text(raw.get("Autó", ""))
        partner_name = self._text(raw.get("Ügyfél", ""))
        bank_account = self._text(raw.get("Bankszámlaszám", ""))
        payment_notice = self._text(raw.get("Közlemény", ""))
        payment_deadline = self._parse_date(raw.get("Fizetési határidő", ""), "Fizetési határidő", issues,
                                            required=False)
        invoice_status = self._text(raw.get("Státusz Számla", ""))
        payment_status = self._text(raw.get("Státusz fizetés", ""))
        kg_debt_huf = self._parse_money_int(raw.get("KG tartozik", ""), "KG tartozik", issues, required=False,
                                            absolute=True)
        note = self._text(raw.get("Megjegyzés", ""))

        self._validate_required_text(source_account, "Számla", issues)
        self._validate_required_text(source_cost_center, "Koltseghely", issues)
        self._validate_required_text(car_name, "Autó", issues)
        self._validate_required_text(partner_name, "Ügyfél", issues)

        if source_account and source_account not in SOURCE_ACCOUNT_VALUES:
            issues.append(
                ValidationIssue("Számla", "UNKNOWN_SOURCE_ACCOUNT", f"Ismeretlen Számla érték: {source_account}"))
        if source_cost_center and transaction_type == "UNKNOWN":
            issues.append(ValidationIssue("Koltseghely", "UNKNOWN_KOLTSEGHELY",
                                          f"Ismeretlen Koltseghely érték: {source_cost_center}"))
        if invoice_status not in INVOICE_STATUS_VALUES:
            issues.append(ValidationIssue("Státusz Számla", "UNKNOWN_INVOICE_STATUS",
                                          f"Ismeretlen Státusz Számla érték: {invoice_status}"))
        if payment_status not in PAYMENT_STATUS_VALUES:
            issues.append(ValidationIssue("Státusz fizetés", "UNKNOWN_PAYMENT_STATUS",
                                          f"Ismeretlen Státusz fizetés érték: {payment_status}"))

        if net_amount_huf is not None and source_net is not None:
            calculated = Decimal(net_amount_huf)
            if abs(calculated - source_net) > Decimal("1"):
                issues.append(
                    ValidationIssue(
                        "Osszeg (netto)",
                        "NET_AMOUNT_MISMATCH",
                        f"A forrás nettó ({source_net}) eltér a számolt nettótól ({calculated})",
                        severity="WARNING",
                    )
                )

        if transaction_type == "PURCHASE" and payment_status == "Fizetésre vár (vétel)" and not bank_account:
            issues.append(ValidationIssue("Bankszámlaszám", "MISSING_BANK_ACCOUNT",
                                          "Vásárlási utaláshoz hiányzik a bankszámlaszám"))


        has_error = any(issue.severity == "ERROR" for issue in issues)
        has_warning = any(issue.severity == "WARNING" for issue in issues)
        normalized_status = "INVALID" if has_error else "WARNING" if has_warning else "VALID"

        return NormalizedTransaction(
            sheet_row_id=sheet_row_id,
            source_row_number=source_row_number,
            external_id=external_id,
            transaction_date=transaction_date,
            source_account=source_account,
            gross_amount_huf=gross_amount_huf,
            vat_rate=vat_rate,
            net_amount_huf=net_amount_huf,
            source_cost_center=source_cost_center,
            transaction_type=transaction_type,
            car_name=car_name,
            partner_name=partner_name,
            bank_account=bank_account,
            payment_notice=payment_notice,
            payment_deadline=payment_deadline,
            invoice_status=invoice_status,
            payment_status=payment_status,
            kg_debt_huf=kg_debt_huf,
            note=note,
            normalized_status=normalized_status,
            issues=issues,
        )

    def _upsert_transaction(self, cur, tx: NormalizedTransaction) -> int:
        timestamp = now_iso()
        cur.execute(
            "SELECT id FROM finance_transactions WHERE sheet_row_id = ?",
            (tx.sheet_row_id,),
        )
        existing = cur.fetchone()

        values = (
            tx.source_row_number,
            tx.external_id,
            tx.transaction_date,
            tx.source_account,
            tx.gross_amount_huf,
            tx.vat_rate,
            tx.net_amount_huf,
            tx.source_cost_center,
            tx.transaction_type,
            tx.car_name,
            tx.partner_name,
            tx.bank_account,
            tx.payment_notice,
            tx.payment_deadline,
            tx.invoice_status,
            tx.payment_status,
            tx.kg_debt_huf,
            tx.note,
            tx.normalized_status,
            timestamp,
            tx.sheet_row_id,
        )

        if existing:
            cur.execute(
                """
                UPDATE finance_transactions
                SET source_row_number = ?, external_id = ?, transaction_date = ?, source_account = ?,
                    gross_amount_huf = ?, vat_rate = ?, net_amount_huf = ?, source_cost_center = ?,
                    transaction_type = ?, car_name = ?, partner_name = ?, bank_account = ?, payment_notice = ?,
                    payment_deadline = ?, invoice_status = ?, payment_status = ?, kg_debt_huf = ?, note = ?,
                    normalized_status = ?, updated_at = ?
                WHERE sheet_row_id = ?
                """,
                values,
            )
            return int(existing["id"])

        cur.execute(
            """
            INSERT INTO finance_transactions (
                sheet_row_id, source_row_number, external_id, transaction_date, source_account,
                gross_amount_huf, vat_rate, net_amount_huf, source_cost_center, transaction_type,
                car_name, partner_name, bank_account, payment_notice, payment_deadline,
                invoice_status, payment_status, kg_debt_huf, note, normalized_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tx.sheet_row_id,
                tx.source_row_number,
                tx.external_id,
                tx.transaction_date,
                tx.source_account,
                tx.gross_amount_huf,
                tx.vat_rate,
                tx.net_amount_huf,
                tx.source_cost_center,
                tx.transaction_type,
                tx.car_name,
                tx.partner_name,
                tx.bank_account,
                tx.payment_notice,
                tx.payment_deadline,
                tx.invoice_status,
                tx.payment_status,
                tx.kg_debt_huf,
                tx.note,
                tx.normalized_status,
                timestamp,
                timestamp,
            ),
        )
        return int(cur.lastrowid)

    def _replace_documents(
            self,
            cur,
            transaction_id: int,
            raw: dict[str, Any],
            unused_links: list[dict[str, str]] | None = None,
            source_row_number: int | None = None,
            document_links_by_cell: dict[tuple[int, str], list[dict[str, str]]] | None = None,
    ) -> None:
        cur.execute(
            "DELETE FROM finance_transaction_documents WHERE transaction_id = ?",
            (transaction_id,),
        )

        timestamp = now_iso()
        document_links_by_cell = document_links_by_cell or {}

        for source_column, document_type in DOCUMENT_COLUMNS.items():
            raw_value = self._text(raw.get(source_column, ""))
            links = document_links_by_cell.get((source_row_number, source_column), [])

            if links:
                for link in links:
                    cur.execute(
                        """
                        INSERT INTO finance_transaction_documents (
                            transaction_id,
                            document_type,
                            source_column,
                            file_name,
                            file_url,
                            raw_value,
                            created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            transaction_id,
                            document_type,
                            source_column,
                            link.get("file_name") or raw_value,
                            link.get("file_url"),
                            link.get("raw_value") or raw_value,
                            timestamp,
                        ),
                    )
                continue

            if raw_value:
                cur.execute(
                    """
                    INSERT INTO finance_transaction_documents (
                        transaction_id,
                        document_type,
                        source_column,
                        file_name,
                        file_url,
                        raw_value,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction_id,
                        document_type,
                        source_column,
                        raw_value,
                        None,
                        raw_value,
                        timestamp,
                    ),
                )

    def _replace_validation_issues(self, cur, transaction_id: int, sheet_row_id: int,
                                   issues: list[ValidationIssue]) -> None:
        cur.execute("DELETE FROM finance_validation_errors WHERE transaction_id = ?", (transaction_id,))
        timestamp = now_iso()
        for issue in issues:
            cur.execute(
                """
                INSERT INTO finance_validation_errors (
                    transaction_id, sheet_row_id, field_name, error_code, error_message, severity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    sheet_row_id,
                    issue.field_name,
                    issue.error_code,
                    issue.error_message,
                    issue.severity,
                    timestamp,
                ),
            )

    def _update_processing_flow_type(self, cur, sheet_row_id: int, transaction_type: str) -> None:
        cur.execute(
            """
            UPDATE sheet_processing
            SET flow_type = ?, updated_at = ?
            WHERE sheet_row_id = ?
            """,
            (transaction_type, now_iso(), sheet_row_id),
        )

    def _parse_int(self, value: Any, field_name: str, issues: list[ValidationIssue],
                   required: bool = False) -> int | None:
        text = self._text(value)
        if not text:
            if required:
                issues.append(
                    ValidationIssue(field_name, "MISSING_REQUIRED_FIELD", f"Hiányzó kötelező mező: {field_name}"))
            return None
        try:
            return int(text)
        except ValueError:
            issues.append(ValidationIssue(field_name, "INVALID_INTEGER", f"Nem egész szám: {text}"))
            return None

    def _parse_date(self, value: Any, field_name: str, issues: list[ValidationIssue],
                    required: bool = False) -> str | None:
        text = self._text(value)
        if not text:
            if required:
                issues.append(
                    ValidationIssue(field_name, "MISSING_REQUIRED_FIELD", f"Hiányzó kötelező mező: {field_name}"))
            return None
        for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date().isoformat()
            except ValueError:
                pass
        issues.append(ValidationIssue(field_name, "INVALID_DATE_FORMAT", f"Nem támogatott dátumformátum: {text}"))
        return None

    def _parse_vat_rate(self, value: Any, issues: list[ValidationIssue]) -> str | None:
        text = self._text(value)
        if not text:
            issues.append(ValidationIssue("Afa %", "MISSING_REQUIRED_FIELD", "Hiányzó kötelező mező: Afa %"))
            return None
        mapped = VAT_RATE_MAP.get(text)
        if mapped is None:
            issues.append(ValidationIssue("Afa %", "INVALID_VAT_RATE", f"Nem támogatott ÁFA érték: {text}"))
            return None
        return mapped

    def _parse_money_int(
            self,
            value: Any,
            field_name: str,
            issues: list[ValidationIssue],
            required: bool = False,
            absolute: bool = True,
    ) -> int | None:
        amount = self._parse_money_decimal(value, field_name, issues, required, absolute)
        if amount is None:
            return None
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _parse_money_decimal(
            self,
            value: Any,
            field_name: str,
            issues: list[ValidationIssue],
            required: bool = False,
            absolute: bool = True,
    ) -> Decimal | None:
        text = self._text(value)
        if not text:
            if required:
                issues.append(
                    ValidationIssue(field_name, "MISSING_REQUIRED_FIELD", f"Hiányzó kötelező mező: {field_name}"))
            return None
        cleaned = text.replace("Ft", "").replace("€", "").replace(" ", "").replace(",", "")
        cleaned = re.sub(r"[^0-9.\-]", "", cleaned)
        if cleaned in {"", "-"}:
            if required:
                issues.append(ValidationIssue(field_name, "INVALID_MONEY_FORMAT", f"Nem pénz érték: {text}"))
            return None
        try:
            amount = Decimal(cleaned)
            return abs(amount) if absolute else amount
        except InvalidOperation:
            issues.append(ValidationIssue(field_name, "INVALID_MONEY_FORMAT", f"Nem pénz érték: {text}"))
            return None

    def _calculate_net_amount(self, gross_amount_huf: int | None, vat_rate: str | None) -> str | None:
        if gross_amount_huf is None or vat_rate is None:
            return None
        gross = Decimal(gross_amount_huf)
        vat = Decimal(vat_rate)
        net = gross / (Decimal("1") + vat)
        return str(net.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _validate_sale_invoice_readiness(
            self,
            transaction_type: str,
            source_cost_center: str,
            invoice_status: str,
            partner_name: str,
            external_id: int | None,
            transaction_date: str | None,
            source_account: str,
            gross_amount_huf: int | None,
            vat_rate: str | None,
            net_amount_huf: str | None,
            car_name: str,
            issues: list[ValidationIssue],
    ) -> None:
        sale_flow_types = {"SALE", "SALE_STOCK_90_DAYS"}

        if transaction_type not in sale_flow_types:
            return

        if source_cost_center not in {"Eladás", "Eladás készlet 90 nap"}:
            issues.append(
                ValidationIssue(
                    "Koltseghely",
                    "INVALID_SALE_COST_CENTER",
                    f"Eladás számlázáshoz nem engedélyezett költséghely: {source_cost_center}",
                )
            )

        normalized_partner = (partner_name or "").strip().lower().replace(".", "")

        if normalized_partner != "kocsiguru kft":
            issues.append(
                ValidationIssue(
                    "Ügyfél",
                    "INVALID_SALE_PARTNER",
                    f"Eladás számlázáshoz az Ügyfél értéke csak 'Kocsiguru Kft.' lehet. Jelenlegi érték: {partner_name}",
                )
            )

        if invoice_status != "Számlára vár":
            issues.append(
                ValidationIssue(
                    "Státusz Számla",
                    "INVALID_SALE_INVOICE_STATUS",
                    f"Eladás számlázás csak 'Számlára vár' státusz esetén indulhat. Jelenlegi érték: {invoice_status}",
                )
            )

        required_values = [
            ("ID", external_id),
            ("Datum", transaction_date),
            ("Számla", source_account),
            ("Osszeg (brutto)", gross_amount_huf),
            ("Afa %", vat_rate),
            ("Osszeg (netto)", net_amount_huf),
            ("Autó", car_name),
        ]

        for field_name, value in required_values:
            if value is None or value == "":
                issues.append(
                    ValidationIssue(
                        field_name,
                        "MISSING_SALE_INVOICE_REQUIRED_FIELD",
                        f"Eladás számlázáshoz hiányzó kötelező mező: {field_name}",
                    )
                )

    def _validate_required_text(self, value: str, field_name: str, issues: list[ValidationIssue]) -> None:
        if not value:
            issues.append(ValidationIssue(field_name, "MISSING_REQUIRED_FIELD", f"Hiányzó kötelező mező: {field_name}"))

    def _text(self, value: Any) -> str:
        return str(value or "").strip()
