from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML, CSS
import logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SAMPLE_DIR = PROJECT_ROOT / "data" / "tmp" / "invoice_samples"
PREVIEW_DIR = PROJECT_ROOT / "data" / "tmp" / "previews"

TEMPLATE_27_AFA = "minta_elonezet_27AFA.html"
TEMPLATE_KAFA = "minta_elonezet_KAFA.html"

CSS_FILE = SAMPLE_DIR / "samples.css"

logging.getLogger("weasyprint").setLevel(logging.ERROR)

def generate_sales_invoice_preview(transaction: dict[str, Any]) -> Path:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    transaction_id = transaction["id"]

    vat_rate = _to_float(transaction.get("vat_rate"))

    template_name = _select_template(vat_rate)

    env = Environment(
        loader=FileSystemLoader(str(SAMPLE_DIR)),
        autoescape=True,
    )

    template = env.get_template(template_name)

    transaction_date = _parse_date(transaction.get("transaction_date"))

    issue_date = date.today()

    due_date = _calculate_due_date(
        issue_date=issue_date,
        source_cost_center=transaction.get("source_cost_center"),
        transaction_type=transaction.get("transaction_type"),
    )

    net_amount = round(_to_float(transaction.get("net_amount_huf")))
    gross_amount = round(_to_float(transaction.get("gross_amount_huf")))
    vat_amount = gross_amount - net_amount

    html = template.render(
        draft_created_date=_format_hu_date(issue_date),
        transaction_date=_format_hu_date(transaction_date),
        due_date=_format_hu_date(due_date),
        car_name=transaction.get("car_name") or "",
        net_amount_huf=_format_huf(net_amount),
        gross_amount_huf=_format_huf(gross_amount),
        vat_amount_huf=_format_huf(vat_amount),
        vat_rate=vat_rate,
        logo_path=(SAMPLE_DIR / "nfo_logo.png").as_uri(),
    )

    output_path = PREVIEW_DIR / f"sales_preview_{transaction_id}.pdf"

    if output_path.exists():
        output_path.unlink()

    HTML(
        string=html,
        base_url=str(SAMPLE_DIR),
    ).write_pdf(
        str(output_path),
        stylesheets=[CSS(filename=str(CSS_FILE))],
    )

    return output_path


def _select_template(vat_rate: float) -> str:
    if vat_rate == 0:
        return TEMPLATE_KAFA

    if vat_rate == 0.27:
        return TEMPLATE_27_AFA

    raise ValueError(f"Unsupported vat_rate for preview template: {vat_rate}")


def _calculate_due_date(
    issue_date: date,
    source_cost_center: str | None,
    transaction_type: str | None,
) -> date:
    if (
        source_cost_center == "Eladás készlet 90 nap"
        or transaction_type == "SALE_STOCK_90_DAYS"
    ):
        return issue_date + timedelta(days=90)

    return issue_date + timedelta(days=8)


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()

    raise ValueError(f"Invalid transaction_date: {value}")


def _format_hu_date(value: date) -> str:
    return f"{value.year}. {value.month:02d}. {value.day:02d}."


def _format_huf(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0

    return float(value)