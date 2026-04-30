from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.database.schema import init_database
from shared.database.connection import get_connection
from services.main_service.app import run_pipeline_once
from services.flow_service.flow_engine import evaluate_transaction
from services.billingo_service.billingo_payload_builder import build_billingo_payload
from services.billingo_service.billingo_client import create_draft_document, BillingoApiError
from services.billingo_service.api_call_logger import log_api_call

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
        sync_status: str = "",
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
                id,
                sheet_row_id,
                source_row_number,
                external_id,
                transaction_date,
                transaction_type,
                source_cost_center,
                source_account,
                car_name,
                partner_name,
                gross_amount_huf,
                vat_rate,
                net_amount_huf,
                invoice_status,
                payment_status,
                normalized_status,
                CASE
                    WHEN transaction_type IN ('SALE', 'SALE_STOCK_90_DAYS')
                     AND source_cost_center IN ('Eladás', 'Eladás készlet 90 nap')
                     AND partner_name = 'Kocsiguru Kft.'
                     AND invoice_status = 'Számlára vár'
                     AND normalized_status = 'VALID'
                    THEN 1
                    ELSE 0
                END AS billingo_ready
            FROM finance_transactions
            {where_sql}
            ORDER BY {sort_by} {sort_dir}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        )

        rows = []

        for row in cur.fetchall():
            row_dict = dict(row)
            flow_result = evaluate_transaction(row_dict)
            row_dict["flow_action"] = flow_result["action"]
            row_dict["flow_reason"] = flow_result["reason"]
            rows.append(row_dict)

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
            "latest_sync_run": latest_sync_run,
            "sync_status": sync_status,
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
        },
    )


@app.post("/sync")
def run_manual_sync():
    run_pipeline_once()
    return RedirectResponse(url="/?sync_status=success", status_code=303)


import json
from fastapi import HTTPException


@app.get("/transactions/{transaction_id}", response_class=HTMLResponse)
def transaction_details(request: Request, transaction_id: int, approval_status: str = "",):
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

    return templates.TemplateResponse(
        "transaction_details.html",
        {
            "request": request,
            "transaction": transaction,
            "validation_errors": validation_errors,
            "documents": documents,
            "raw_json_pretty": raw_json_pretty,
            "approval_status": approval_status,
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

        if flow_result["action"] != "BILLINGO_DRAFT_REQUIRED":
            return RedirectResponse(
                url=f"/transactions/{transaction_id}?approval_status=not_ready",
                status_code=303,
            )

        payload = build_billingo_payload(transaction)

        print("[BILLINGO PAYLOAD]", payload)

        try:
            billingo_response = create_draft_document(payload)

            log_api_call(
                provider="Billingo",
                endpoint="/documents",
                method="POST",
                transaction_id=transaction_id,
                request_payload=payload,
                response_status=201,
                response_payload=billingo_response,
                success=True,
            )

            print("[BILLINGO RESPONSE]", billingo_response)

        except BillingoApiError as exc:
            log_api_call(
                provider="Billingo",
                endpoint="/documents",
                method="POST",
                transaction_id=transaction_id,
                request_payload=payload,
                response_status=exc.status_code,
                response_payload=exc.response_data,
                success=False,
                error_message=str(exc),
            )

            print("[BILLINGO ERROR]", str(exc))

            return RedirectResponse(
                url=f"/transactions/{transaction_id}?approval_status=billingo_error",
                status_code=303,
            )

        print(
            "[FLOW APPROVAL] Billingo draft approved",
            {
                "transaction_id": transaction_id,
                "source_row_number": transaction.get("source_row_number"),
                "car_name": transaction.get("car_name"),
                "partner_name": transaction.get("partner_name"),
                "amount": transaction.get("net_amount_huf"),
            },
        )

    return RedirectResponse(
        url=f"/transactions/{transaction_id}?approval_status=approved",
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
        },
    )