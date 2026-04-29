from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.database.schema import init_database
from shared.database.connection import get_connection
from services.main_service.app import run_pipeline_once

app = FastAPI(title="CarCOM Dashboard")

app.mount("/static", StaticFiles(directory="services/web_service/static"), name="static")
templates = Jinja2Templates(directory="services/web_service/templates")


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    page: int = Query(1, ge=1),
    search: str = "",
    sort_by: str = "source_row_number",
    sort_dir: str = "desc",
    transaction_type: str = "",
    normalized_status: str = "",
):
    init_database()

    page_size = 25
    offset = (page - 1) * page_size

    allowed_sort_columns = {
        "source_row_number",
        "external_id",
        "transaction_date",
        "transaction_type",
        "car_name",
        "partner_name",
        "gross_amount_huf",
        "normalized_status",
    }

    if sort_by not in allowed_sort_columns:
        sort_by = "source_row_number"

    sort_dir = "asc" if sort_dir.lower() == "asc" else "desc"

    where_clauses = []
    params = []

    if search:
        where_clauses.append("""
            (
                CAST(source_row_number AS TEXT) LIKE ?
                OR CAST(external_id AS TEXT) LIKE ?
                OR car_name LIKE ?
                OR partner_name LIKE ?
                OR payment_notice LIKE ?
                OR source_cost_center LIKE ?
            )
        """)
        like_value = f"%{search}%"
        params.extend([like_value] * 6)

    if transaction_type:
        where_clauses.append("transaction_type = ?")
        params.append(transaction_type)

    if normalized_status:
        where_clauses.append("normalized_status = ?")
        params.append(normalized_status)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM finance_transactions
            {where_sql}
            """,
            params,
        )
        total_count = int(cur.fetchone()["count"])

        cur.execute(
            f"""
            SELECT
                source_row_number,
                external_id,
                transaction_date,
                transaction_type,
                car_name,
                partner_name,
                gross_amount_huf,
                vat_rate,
                net_amount_huf,
                invoice_status,
                payment_status,
                normalized_status
            FROM finance_transactions
            {where_sql}
            ORDER BY {sort_by} {sort_dir}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )

        rows = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT transaction_type, COUNT(*) AS count
            FROM finance_transactions
            GROUP BY transaction_type
            ORDER BY transaction_type
        """)
        type_summary = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT normalized_status, COUNT(*) AS count
            FROM finance_transactions
            GROUP BY normalized_status
            ORDER BY normalized_status
        """)
        status_summary = [dict(row) for row in cur.fetchall()]

    total_pages = max((total_count + page_size - 1) // page_size, 1)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "search": search,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "transaction_type": transaction_type,
            "normalized_status": normalized_status,
            "type_summary": type_summary,
            "status_summary": status_summary,
        },
    )


@app.post("/sync")
def run_manual_sync():
    run_pipeline_once()
    return RedirectResponse(url="/", status_code=303)