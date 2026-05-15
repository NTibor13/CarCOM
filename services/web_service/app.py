import os
import json
import math

from pydantic import BaseModel

from fastapi import HTTPException
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.database.schema import init_database
from shared.database.connection import get_connection
from shared.google_auth_errors import GoogleAuthenticationRequiredError
from shared.google_oauth import load_oauth_credentials
from shared.config.settings import settings as app_settings
from services.main_service.app import run_pipeline_once
from services.flow_service.flow_engine import evaluate_transaction
from services.flow_service.flow_executor import FlowExecutor
from services.flow_service.purchase_batch_executor import PurchaseBatchExecutor
from services.payment_batch_service.payment_batch_repository import PaymentBatchRepository
from services.billingo_service.invoice_link_repository import get_latest_invoice_link
from services.web_service.template_filters import (
    format_huf,
    format_vat,
    format_transaction_type,
)

from google.oauth2.credentials import Credentials

from services.mbh_service.auth import exchange_authorization_code
from services.mbh_service.token_manager import save_account_token_response
from services.mbh_service.payment_initiation import create_domestic_payment_consent
from services.web_service.routers import mbh_account_settings, mbh_account_sync

app = FastAPI(title="CarCOM")

app.mount("/static", StaticFiles(directory="services/web_service/static"), name="static")
app.include_router(mbh_account_settings.router)
app.include_router(mbh_account_sync.router)
templates = Jinja2Templates(directory="services/web_service/templates")

templates.env.filters["format_huf"] = format_huf
templates.env.filters["format_vat"] = format_vat
templates.env.filters["format_transaction_type"] = format_transaction_type


@app.get("/", response_class=HTMLResponse)
def dashboard(
        request: Request,
        purchase_page: int = Query(1, ge=1),
        sales_page: int = Query(1, ge=1),
        search: str = "",
        sort_by: str = "source_row_number",
        sort_dir: str = "desc",
        transaction_type: str = "",
        normalized_status: str = "",
        sync_status: str = "",
):
    init_database()

    page_size = 25

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
                id,
                sheet_row_id,
                source_row_number,
                external_id,
                transaction_date,
                transaction_type,
                source_cost_center,
                source_account,
                car_name,
                bank_account,
                payment_notice,
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
            """,
            params,
        )

        rows = []

        for row in cur.fetchall():
            row_dict = dict(row)
            flow_result = evaluate_transaction(row_dict)
            row_dict["flow_action"] = flow_result["action"]
            row_dict["flow_reason"] = flow_result["reason"]
            rows.append(row_dict)

        all_purchase_rows = [
            row for row in rows
            if row.get("transaction_type") in (
                "PURCHASE",
                "PURCHASE FROM INDIVIDUAL",
            )
        ]

        all_sales_rows = [
            row for row in rows
            if row.get("transaction_type") in (
                "SALE",
                "SALE_STOCK_90_DAYS",
            )
        ]

        purchase_total_count = len(all_purchase_rows)
        sales_total_count = len(all_sales_rows)

        purchase_total_pages = max(1, math.ceil(purchase_total_count / page_size))
        sales_total_pages = max(1, math.ceil(sales_total_count / page_size))

        purchase_page = max(1, min(purchase_page, purchase_total_pages))
        sales_page = max(1, min(sales_page, sales_total_pages))

        purchase_start = (purchase_page - 1) * page_size
        purchase_end = purchase_start + page_size

        sales_start = (sales_page - 1) * page_size
        sales_end = sales_start + page_size

        purchase_rows = all_purchase_rows[purchase_start:purchase_end]
        sales_rows = all_sales_rows[sales_start:sales_end]

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

        cur.execute("""
            SELECT
                id,
                service_name,
                started_at,
                finished_at,
                status,
                rows_read,
                inserted_count,
                updated_count,
                deleted_count,
                error_message
            FROM sync_runs
            ORDER BY started_at DESC
            LIMIT 1
        """)
        latest_sync_run = cur.fetchone()
        latest_sync_run = dict(latest_sync_run) if latest_sync_run else None

    total_pages = 1

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
            "purchase_rows": purchase_rows,
            "sales_rows": sales_rows,
            "page": 1,
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
            "latest_sync_run": latest_sync_run,
            "sync_status": sync_status,
            "active_page": "dashboard",
            "purchase_page": purchase_page,
            "purchase_total_pages": purchase_total_pages,
            "purchase_total_count": purchase_total_count,
            "sales_page": sales_page,
            "sales_total_pages": sales_total_pages,
            "sales_total_count": sales_total_count,
        },
    )


@app.get("/validation-errors", response_class=HTMLResponse)
def validation_errors(
        request: Request,
        page: int = Query(1, ge=1),
        search: str = "",
        severity: str = "",
        error_code: str = "",
):
    init_database()

    page_size = 25
    offset = (page - 1) * page_size

    where_clauses = []
    params = []

    if search:
        where_clauses.append("""
            (
                CAST(t.source_row_number AS TEXT) LIKE ?
                OR CAST(t.external_id AS TEXT) LIKE ?
                OR t.car_name LIKE ?
                OR t.partner_name LIKE ?
                OR v.field_name LIKE ?
                OR v.error_message LIKE ?
            )
        """)
        like_value = f"%{search}%"
        params.extend([like_value] * 6)

    if severity:
        where_clauses.append("v.severity = ?")
        params.append(severity)

    if error_code:
        where_clauses.append("v.error_code = ?")
        params.append(error_code)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM finance_validation_errors v
            LEFT JOIN finance_transactions t ON t.id = v.transaction_id
            {where_sql}
            """,
            params,
        )
        total_count = int(cur.fetchone()["count"])

        cur.execute(
            f"""
            SELECT
                v.id,
                v.severity,
                v.field_name,
                v.error_code,
                v.error_message,
                v.created_at,
                t.source_row_number,
                t.external_id,
                t.transaction_type,
                t.car_name,
                t.partner_name,
                t.normalized_status
            FROM finance_validation_errors v
            LEFT JOIN finance_transactions t ON t.id = v.transaction_id
            {where_sql}
            ORDER BY t.source_row_number DESC, v.severity ASC, v.field_name ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
        rows = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT severity, COUNT(*) AS count
            FROM finance_validation_errors
            GROUP BY severity
            ORDER BY severity
        """)
        severity_summary = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT error_code, COUNT(*) AS count
            FROM finance_validation_errors
            GROUP BY error_code
            ORDER BY count DESC
        """)
        error_code_summary = [dict(row) for row in cur.fetchall()]

    total_pages = max((total_count + page_size - 1) // page_size, 1)

    return templates.TemplateResponse(
        "validation_errors.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "search": search,
            "severity": severity,
            "error_code": error_code,
            "severity_summary": severity_summary,
            "error_code_summary": error_code_summary,
            "active_page": "validation_errors",
        },
    )


@app.post("/sync")
def run_manual_sync(request: Request):
    try:
        run_pipeline_once()
    except GoogleAuthenticationRequiredError as exc:
        return templates.TemplateResponse(
            "sync_error.html",
            {
                "request": request,
                "active_page": "sync_runs",
                "message": str(exc),
                "error_message": str(exc),
            },
            status_code=401,
        )

    return RedirectResponse(url="/", status_code=303)


@app.get("/transactions/{transaction_id}", response_class=HTMLResponse)
def transaction_details(request: Request, transaction_id: int, approval_status: str = "", ):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT *
            FROM finance_transactions
            WHERE id = ?
        """, (transaction_id,))
        transaction = cur.fetchone()
        from services.flow_service.flow_engine import evaluate_transaction

        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        transaction = dict(transaction)

        flow_result = evaluate_transaction(transaction)
        transaction["flow_action"] = flow_result["action"]
        transaction["flow_reason"] = flow_result["reason"]

        cur.execute("""
            SELECT raw_json
            FROM sheet_rows_raw
            WHERE id = ?
        """, (transaction["sheet_row_id"],))
        raw_row = cur.fetchone()

        raw_json_pretty = ""
        if raw_row and raw_row["raw_json"]:
            raw_json_pretty = json.dumps(
                json.loads(raw_row["raw_json"]),
                ensure_ascii=False,
                indent=2,
            )

        cur.execute("""
            SELECT *
            FROM finance_validation_errors
            WHERE transaction_id = ?
            ORDER BY severity, field_name
        """, (transaction_id,))
        validation_errors = [dict(row) for row in cur.fetchall()]

        cur.execute("""
            SELECT *
            FROM finance_transaction_documents
            WHERE transaction_id = ?
            ORDER BY document_type, file_name
        """, (transaction_id,))
        documents = [dict(row) for row in cur.fetchall()]

        billingo_invoice_link = get_latest_invoice_link(transaction_id)

        cur.execute(
            """
            SELECT *
            FROM flow_runs
            WHERE transaction_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (transaction_id,),
        )
        latest_flow_run = cur.fetchone()
        latest_flow_run = dict(latest_flow_run) if latest_flow_run else None

        cur.execute(
            """
            SELECT
                pbi.id AS payment_batch_item_id,
                pbi.status AS payment_batch_item_status,
                pbi.amount_huf,
                pbi.payment_notice,
                pb.id AS payment_batch_id,
                pb.status AS payment_batch_status,
                pb.created_at AS payment_batch_created_at
            FROM payment_batch_items pbi
            JOIN payment_batches pb ON pb.id = pbi.batch_id
            WHERE pbi.transaction_id = ?
            ORDER BY pbi.id DESC
            LIMIT 1
            """,
            (transaction_id,),
        )
        payment_batch_info = cur.fetchone()
        payment_batch_info = dict(payment_batch_info) if payment_batch_info else None

    return templates.TemplateResponse(
        "transaction_details.html",
        {
            "request": request,
            "transaction": transaction,
            "validation_errors": validation_errors,
            "documents": documents,
            "raw_json_pretty": raw_json_pretty,
            "approval_status": approval_status,
            "billingo_invoice_link": billingo_invoice_link,
            "latest_flow_run": latest_flow_run,
            "active_page": "dashboard",
            "payment_batch_info": payment_batch_info,
        },
    )


@app.post("/transactions/{transaction_id}/approve-billingo")
def approve_billingo_draft(transaction_id: int):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        transaction = cur.fetchone()

        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found")

        transaction = dict(transaction)
        flow_result = evaluate_transaction(transaction)

        if flow_result["action"] != "SALES_READY":
            return RedirectResponse(
                url=f"/transactions/{transaction_id}?approval_status=not_ready",
                status_code=303,
            )

        try:
            result = FlowExecutor().run_sale_flow(transaction["id"])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        status = result["status"]

        return RedirectResponse(
            url=f"/transactions/{transaction['id']}?flow_status={status}",
            status_code=303,
        )


@app.get("/api-logs", response_class=HTMLResponse)
def api_logs(
        request: Request,
        page: int = Query(1, ge=1),
        provider: str = "",
        success: str = "",
):
    init_database()

    page_size = 25
    offset = (page - 1) * page_size

    where_clauses = []
    params = []

    if provider:
        where_clauses.append("provider = ?")
        params.append(provider)

    if success in ("0", "1"):
        where_clauses.append("success = ?")
        params.append(int(success))

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM api_call_logs
            {where_sql}
            """,
            params,
        )
        total_count = int(cur.fetchone()["count"])

        cur.execute(
            f"""
            SELECT
                l.id,
                l.provider,
                l.endpoint,
                l.method,
                l.transaction_id,
                l.response_status,
                l.success,
                l.error_message,
                l.created_at,
                t.source_row_number,
                t.car_name,
                t.partner_name
            FROM api_call_logs l
            LEFT JOIN finance_transactions t
                ON t.id = l.transaction_id
            {where_sql}
            ORDER BY l.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )

        rows = [dict(row) for row in cur.fetchall()]

        total_pages = max((total_count + page_size - 1) // page_size, 1)

    return templates.TemplateResponse(
        "api_logs.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "provider": provider,
            "success": success,
            "active_page": "api_logs",
        },
    )


@app.get("/api-logs/{log_id}", response_class=HTMLResponse)
def api_log_detail(request: Request, log_id: int):
    init_database()
    import json

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                l.*,
                t.source_row_number,
                t.car_name,
                t.partner_name,
                t.external_id
            FROM api_call_logs l
            LEFT JOIN finance_transactions t
                ON t.id = l.transaction_id
            WHERE l.id = ?
            """,
            (log_id,),
        )

        log = cur.fetchone()

        if log is None:
            raise HTTPException(status_code=404, detail="API log not found")

        log = dict(log)

        def pretty_json(value):
            if not value:
                return ""

            try:
                parsed = json.loads(value)
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                return value

        log["request_json_pretty"] = pretty_json(log.get("request_json"))
        log["response_json_pretty"] = pretty_json(log.get("response_json"))

    return templates.TemplateResponse(
        "api_log_detail.html",
        {
            "request": request,
            "log": log,
            "active_page": "api_logs",
        },
    )


@app.get("/api/flow/{transaction_id}")
def get_flow(transaction_id: int):
    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT *
            FROM flow_runs
            WHERE transaction_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (transaction_id,),
        )
        flow_run = cur.fetchone()

        if not flow_run:
            return {"flow_run": None, "steps": []}

        flow_run = dict(flow_run)

        cur.execute(
            """
            SELECT *
            FROM flow_step_logs
            WHERE flow_run_id = ?
            ORDER BY step_order
            """,
            (flow_run["id"],),
        )
        steps = [dict(row) for row in cur.fetchall()]

    return {
        "flow_run": flow_run,
        "steps": steps,
        "active_page": "dashboard",
    }


@app.get("/sync-runs", response_class=HTMLResponse)
def sync_runs(
        request: Request,
        page: int = Query(1, ge=1),
        status: str = "",
):
    init_database()

    page_size = 25
    offset = (page - 1) * page_size

    where_clauses = []
    params = []

    if status:
        where_clauses.append("status = ?")
        params.append(status)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM sync_runs
            {where_sql}
            """,
            params,
        )
        total_count = int(cur.fetchone()["count"])

        cur.execute(
            f"""
            SELECT
                id,
                service_name,
                started_at,
                finished_at,
                status,
                source_name,
                source_identifier,
                rows_read,
                inserted_count,
                updated_count,
                deleted_count,
                error_message
            FROM sync_runs
            {where_sql}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )
        rows = [dict(row) for row in cur.fetchall()]

    total_pages = max((total_count + page_size - 1) // page_size, 1)

    return templates.TemplateResponse(
        "sync_runs.html",
        {
            "request": request,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "status": status,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    init_database()

    integrations = [
        {
            "name": "Google Sheets API",
            "configured": bool(
                os.getenv("GOOGLE_SHEET_ID")
                and os.getenv("GOOGLE_WORKSHEET_NAME")
                and os.getenv("GOOGLE_RANGE")
            ),
        },
        {
            "name": "Google Drive API",
            "configured": bool(
                os.getenv("BILLINGO_INVOICE_DRIVE_FOLDER_ID")
                and os.getenv("GOOGLE_CREDENTIALS_FILE")
            ),
        },
        {
            "name": "Billingo API",
            "configured": bool(os.getenv("BILLINGO_API_KEY")),
        },
    ]

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                group_name,
                value,
                normalized_value,
                is_active
            FROM lookup_values
            ORDER BY group_name, value
            """
        )
        lookup_rows = [dict(row) for row in cur.fetchall()]

    grouped_lookup_values = {}
    for row in lookup_rows:
        grouped_lookup_values.setdefault(row["group_name"], []).append(row)
    google_auth = get_google_oauth_status()
    mbh_account_info = get_mbh_account_info_status_for_ui()

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "environment": os.getenv("APP_ENV", "development"),
            "database_type": "SQLite",
            "integrations": integrations,
            "grouped_lookup_values": grouped_lookup_values,
            "google_auth": google_auth,
            "mbh_account_info": mbh_account_info,
            "mbh_auth": request.query_params.get("mbh_auth"),
            "mbh_status": request.query_params.get("mbh_status"),
            "mbh_message": request.query_params.get("mbh_message"),
            "google_auth_result": request.query_params.get("google_auth"),
        },
    )


def get_google_oauth_status():
    token_file = app_settings.google_oauth_token_file

    if not os.path.exists(token_file):
        return {
            "mode": "OAuth",
            "status": "HIÁNYZIK",
            "has_refresh_token": False,
        }

    try:
        creds = Credentials.from_authorized_user_file(token_file)

        return {
            "mode": "OAuth",
            "status": "ÉRVÉNYES" if creds.valid else "LEJÁRT" if creds.expired else "HIBÁS",
            "has_refresh_token": bool(creds.refresh_token),
        }

    except Exception:
        return {
            "mode": "OAuth",
            "status": "HIBÁS",
            "has_refresh_token": False,
        }


@app.post("/transactions/{transaction_id}/rerun-flow")
def rerun_transaction_flow(transaction_id: int):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        )
        transaction = cur.fetchone()

    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction = dict(transaction)
    flow_result = evaluate_transaction(transaction)

    executor = FlowExecutor()

    if flow_result["action"] == "SALES_READY":
        result = executor.run_sale_flow(
            transaction_id=transaction_id,
            force_new_run=True,
        )

    elif flow_result["action"] == "PURCHASE_PAYMENT_READY":
        result = executor.run_purchase_flow(
            transaction_id=transaction_id,
            force_new_run=True,
        )

    else:
        return RedirectResponse(
            url=f"/transactions/{transaction_id}?approval_status=not_ready",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/transactions/{transaction_id}?flow_status={result['status']}",
        status_code=303,
    )


@app.get("/settings/google-auth/start")
def start_google_auth():
    try:
        load_oauth_credentials(interactive=True)
    except Exception as exc:
        print(f"Google OAuth start failed: {exc}")
        return RedirectResponse(
            url=f"/settings?google_auth=failed&google_auth_message={str(exc)}",
            status_code=303,
        )

    return RedirectResponse(url="/settings?google_auth=success", status_code=303)


@app.get("/mbh/callback")
def mbh_callback(request: Request):
    code = request.query_params.get("code")

    if not code:
        return RedirectResponse(url="/settings?mbh_auth=failed", status_code=303)

    status, text, _headers = exchange_authorization_code(code)

    if status != 200:
        return RedirectResponse(url="/settings?mbh_auth=failed", status_code=303)

    save_account_token_response(text)

    return RedirectResponse(url="/settings?mbh_auth=success", status_code=303)


class TestDomesticPaymentConsentRequest(BaseModel):
    amount: str = "1000.00"
    currency: str = "HUF"
    creditor_name: str = "Teszt Partner"
    creditor_scheme_name: str = "HU.CGI"
    creditor_identification: str
    reference: str | None = "CARCOM-TEST"


@app.post("/experiments/payment/test-domestic-consent")
def test_domestic_payment_consent(payload: TestDomesticPaymentConsentRequest):
    status, text, headers = create_domestic_payment_consent(
        amount=payload.amount,
        currency=payload.currency,
        creditor_name=payload.creditor_name,
        creditor_scheme_name=payload.creditor_scheme_name,
        creditor_identification=payload.creditor_identification,
        reference=payload.reference,
    )

    try:

        response_body = json.loads(text)
    except Exception:
        response_body = text

    return {
        "status_code": status,
        "response": response_body,
        "headers": headers,
    }


def get_mbh_account_info_status_for_ui():
    try:
        from services.web_service.routers.mbh_account_settings import (
            get_mbh_account_info_status,
        )

        status = get_mbh_account_info_status() or {}

    except Exception as exc:
        status = {
            "connected": False,
            "needs_reauth": True,
            "api_type": "account_info",
            "message": f"MBH Account Info státusz nem olvasható: {str(exc)}",
        }

    status.setdefault("connected", False)
    status.setdefault("needs_reauth", True)
    status.setdefault("api_type", "account_info")
    status.setdefault("message", "Az MBH Account Info kapcsolat jelenleg nincs aktív használatban.")

    if status.get("connected"):
        status.setdefault("ui_status", "success")
        status.setdefault("ui_label", "Kapcsolódva")
        status.setdefault("ui_description", "Az MBH Account Info kapcsolat aktív.")
    elif status.get("needs_reauth"):
        status.setdefault("ui_status", "warning")
        status.setdefault("ui_label", "Újrahitelesítés szükséges")
        status.setdefault("ui_description", status.get("message"))
    else:
        status.setdefault("ui_status", "inactive")
        status.setdefault("ui_label", "Nincs aktív kapcsolat")
        status.setdefault("ui_description", status.get("message"))

    return status


@app.post("/settings/mbh/account-info/create-consent-ui")
def create_mbh_account_info_consent_ui():
    from services.web_service.routers.mbh_account_settings import (
        create_mbh_account_info_consent,
    )

    create_mbh_account_info_consent()

    return RedirectResponse(
        url="/settings?mbh_status=consent_created",
        status_code=303,
    )


@app.post("/settings/mbh/account-info/sync-ui")
def run_mbh_account_info_sync_ui(days_back: int = 7):
    from services.web_service.routers.mbh_account_sync import (
        run_mbh_account_info_sync,
    )

    run_mbh_account_info_sync(days_back=days_back)

    return RedirectResponse(
        url="/settings?mbh_status=sync_success",
        status_code=303,
    )


@app.post("/transactions/{transaction_id}/approve-purchase")
def approve_purchase_flow(transaction_id: int):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM finance_transactions WHERE id = ?",
            (transaction_id,),
        )
        transaction = cur.fetchone()

    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")

    transaction = dict(transaction)
    flow_result = evaluate_transaction(transaction)

    if flow_result["action"] != "PURCHASE_PAYMENT_READY":
        return RedirectResponse(
            url=f"/transactions/{transaction_id}?approval_status=not_ready",
            status_code=303,
        )

    result = FlowExecutor().run_purchase_flow(transaction_id)

    return RedirectResponse(
        url=f"/transactions/{transaction_id}?flow_status={result['status']}",
        status_code=303,
    )


@app.get("/payment-batches", response_class=HTMLResponse)
def payment_batches(request: Request):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                pb.id,
                pb.status,
                pb.created_at,
                pb.updated_at,
                pb.export_format,
                pb.export_file_name,
                pb.export_file_path,
                pb.exported_at,
                COUNT(pbi.id) AS item_count,
                COALESCE(SUM(pbi.amount_huf), 0) AS total_amount_huf
            FROM payment_batches pb
            LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
            GROUP BY pb.id
            ORDER BY pb.id DESC
        """)
        batches = [dict(row) for row in cur.fetchall()]

    return templates.TemplateResponse(
        "payment_batches.html",
        {
            "request": request,
            "batches": batches,
            "active_page": "payment_batches",
        },
    )


@app.get("/payment-batches/{batch_id}", response_class=HTMLResponse)
def payment_batch_details(request: Request, batch_id: int):
    init_database()

    with get_connection() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                pb.id,
                pb.status,
                pb.created_at,
                pb.updated_at,
                pb.export_format,
                pb.export_file_name,
                pb.export_file_path,
                pb.exported_at,
                COUNT(pbi.id) AS item_count,
                COALESCE(SUM(pbi.amount_huf), 0) AS total_amount_huf
            FROM payment_batches pb
            LEFT JOIN payment_batch_items pbi ON pbi.batch_id = pb.id
            WHERE pb.id = ?
            GROUP BY pb.id
        """, (batch_id,))
        batch = cur.fetchone()

        if batch is None:
            raise HTTPException(status_code=404, detail="Payment batch not found")

        batch = dict(batch)

        cur.execute("""
            SELECT
                pbi.id AS payment_batch_item_id,
                pbi.status AS payment_batch_item_status,
                pbi.creditor_name,
                pbi.creditor_bank_account,
                pbi.amount_huf,
                pbi.payment_notice,
                pbi.created_at,
                t.id AS transaction_id,
                t.source_row_number,
                t.external_id,
                t.car_name,
                t.partner_name,
                t.transaction_type,
                t.payment_status
            FROM payment_batch_items pbi
            JOIN finance_transactions t ON t.id = pbi.transaction_id
            WHERE pbi.batch_id = ?
            ORDER BY pbi.id ASC
        """, (batch_id,))
        items = [dict(row) for row in cur.fetchall()]

    return templates.TemplateResponse(
        "payment_batch_details.html",
        {
            "request": request,
            "batch": batch,
            "items": items,
            "active_page": "payment_batches",
        },
    )


@app.post("/payment-batches/create-from-transactions")
async def create_payment_batch_from_transactions(request: Request):
    init_database()

    form = await request.form()
    transaction_ids = [
        int(value)
        for value in form.getlist("transaction_ids")
        if str(value).isdigit()
    ]

    if not transaction_ids:
        return RedirectResponse(
            url="/?payment_batch_status=no_selection",
            status_code=303,
        )

    ready_transaction_ids = []

    with get_connection() as conn:
        cur = conn.cursor()

        for transaction_id in transaction_ids:
            cur.execute("""
                SELECT *
                FROM finance_transactions
                WHERE id = ?
            """, (transaction_id,))
            row = cur.fetchone()

            if row is None:
                continue

            transaction = dict(row)
            flow_result = evaluate_transaction(transaction)

            if flow_result["action"] == "PURCHASE_PAYMENT_READY":
                ready_transaction_ids.append(transaction_id)

    if not ready_transaction_ids:
        return RedirectResponse(
            url="/?payment_batch_status=no_ready_items",
            status_code=303,
        )

    result = PurchaseBatchExecutor().run(transaction_ids)

    if not result.get("payment_batch_id"):
        return RedirectResponse(
            url=f"/?payment_batch_status={result['status']}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/payment-batches/{result['payment_batch_id']}",
        status_code=303,
    )


@app.get("/payment-batches/{batch_id}/download-export")
def download_payment_batch_export(batch_id: int):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT export_file_path, export_file_name, status
            FROM payment_batches
            WHERE id = ?
            """,
            (batch_id,),
        )
        row = cur.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Payment batch not found")

        if not row["export_file_path"]:
            raise HTTPException(status_code=404, detail="Payment export not found")

        if row["status"] == "XML_DONE":
            cur.execute(
                """
                UPDATE payment_batches
                SET status = 'EXPORTED',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (batch_id,),
            )
            conn.commit()

    return FileResponse(
        path=row["export_file_path"],
        filename=row["export_file_name"],
        media_type="application/xml",
    )
