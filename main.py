import os
import io
import json
import time
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
import pandas as pd

from extractor import process_file
from llm import extract_invoice_data
from vat_rules import classify_vat
from audit import (
    init_db, log_extraction, log_approval,
    log_rejection, get_all_records, get_summary_stats
)
from exporter import to_csv_bytes, to_xero_csv_bytes, generate_exception_report
from matcher import load_bank_csv, find_match

# ── Init ──────────────────────────────────────────────────────────────────────
app: FastAPI = FastAPI(title="VatOps AI")
init_db()

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_sessions: dict[str, dict] = {}

def get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {"processed": [], "bank_df": None}
    return _sessions[session_id]


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing():
    return FileResponse(BASE_DIR / "landing.html")

@app.get("/app", response_class=HTMLResponse)
async def app_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# ── Bank upload ───────────────────────────────────────────────────────────────
@app.post("/api/bank")
async def upload_bank(request: Request, file: UploadFile = File(...)):
    session_id = request.cookies.get("vatops_session", "default")
    session = get_session(session_id)

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        df = load_bank_csv(tmp_path)
        session["bank_df"] = df
        return {"ok": True, "count": len(df), "message": f"{len(df)} transactions loaded"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        os.unlink(tmp_path)


# ── Invoice processing ────────────────────────────────────────────────────────
@app.post("/api/process")
async def process_invoice(request: Request, file: UploadFile = File(...)):
    session_id = request.cookies.get("vatops_session", "default")
    session = get_session(session_id)

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        start = time.time()
        text, status = process_file(tmp_path)

        if status in ("scanned", "image"):
            return {"status": "exception", "filename": file.filename,
                    "error": "Scanned or image-based — manual entry required"}
        if status.startswith("error"):
            return {"status": "exception", "filename": file.filename, "error": status}

        invoice, ok = extract_invoice_data(text)
        if not ok:
            return {"status": "exception", "filename": file.filename, "error": invoice.notes}

        vat_result = classify_vat(
            invoice.total_amount, invoice.vat_amount, invoice.vat_rate,
            vat_field_confidence=invoice.field_confidence.vat_amount
        )

        match_result = None
        if session["bank_df"] is not None:
            match_result = find_match(invoice.supplier_name, invoice.total_amount,
                                      invoice.invoice_date, session["bank_df"])

        processing_time = round(time.time() - start, 2)
        audit_id = log_extraction(
            filename=file.filename,
            extracted_data=invoice.model_dump(),
            vat_category=vat_result.category,
            vat_flags=vat_result.flags,
            confidence=invoice.confidence,
            processing_time=processing_time,
            session_id=session_id
        )

        result = {
            "audit_id": audit_id, "filename": file.filename, "status": "pending",
            "processing_time": processing_time,
            "supplier_name": invoice.supplier_name, "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date, "total_amount": invoice.total_amount,
            "vat_amount": invoice.vat_amount, "vat_rate": vat_result.rate,
            "currency": invoice.currency, "line_items": invoice.line_items,
            "confidence": invoice.confidence,
            "field_confidence": invoice.field_confidence.model_dump(),
            "reasoning": invoice.reasoning, "notes": invoice.notes,
            "vat_category": vat_result.category, "vat_flags": vat_result.flags,
            "vat_valid": vat_result.is_valid, "vat_certainty": vat_result.certainty,
            "bank_matched": match_result.matched if match_result else False,
            "bank_description": match_result.bank_description if match_result else "",
            "bank_amount": match_result.bank_amount if match_result else 0.0,
            "bank_confidence": match_result.confidence if match_result else 0.0,
            "match_reason": match_result.match_reason if match_result else "",
        }
        session["processed"].append(result)
        return result
    finally:
        os.unlink(tmp_path)


# ── Approve ───────────────────────────────────────────────────────────────────
@app.post("/api/approve/{audit_id}")
async def approve_invoice(request: Request, audit_id: int, data: dict):
    session_id = request.cookies.get("vatops_session", "default")
    session = get_session(session_id)

    for rec in session["processed"]:
        if rec.get("audit_id") == audit_id:
            edits = {k: {"before": rec.get(k), "after": data.get(k)}
                     for k in ["supplier_name", "invoice_number", "invoice_date",
                               "total_amount", "vat_amount", "vat_rate"]
                     if str(rec.get(k)) != str(data.get(k))}
            log_approval(audit_id, data, edits)
            rec.update(data)
            rec["status"] = "approved"
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Record not found")


# ── Reject ────────────────────────────────────────────────────────────────────
@app.post("/api/reject/{audit_id}")
async def reject_invoice(request: Request, audit_id: int):
    session_id = request.cookies.get("vatops_session", "default")
    session = get_session(session_id)

    for rec in session["processed"]:
        if rec.get("audit_id") == audit_id:
            log_rejection(audit_id, "Rejected by user")
            rec["status"] = "rejected"
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Record not found")


# ── Session data ──────────────────────────────────────────────────────────────
@app.get("/api/records")
async def get_records(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    return {"records": get_session(session_id)["processed"]}


# ── Exports ───────────────────────────────────────────────────────────────────
@app.get("/api/export/csv")
async def export_csv(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    approved = [r for r in get_session(session_id)["processed"] if r.get("status") == "approved"]
    data = to_csv_bytes(approved)
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=vatops_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.get("/api/export/xero")
async def export_xero(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    approved = [r for r in get_session(session_id)["processed"] if r.get("status") == "approved"]
    data = to_xero_csv_bytes(approved)
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=xero_{datetime.now().strftime('%Y%m%d')}.csv"})

@app.get("/api/export/exceptions")
async def export_exceptions(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    flagged = [r for r in get_session(session_id)["processed"]
               if r.get("vat_flags") and r["vat_flags"] not in ([], "[]")]
    data = generate_exception_report(flagged)
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=exceptions_{datetime.now().strftime('%Y%m%d')}.csv"})


# ── Audit log ─────────────────────────────────────────────────────────────────
@app.get("/api/audit")
async def audit_log(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    return {"records": get_all_records(session_id), "stats": get_summary_stats(session_id)}

@app.get("/api/audit/export")
async def export_audit(request: Request):
    session_id = request.cookies.get("vatops_session", "default")
    df = pd.DataFrame(get_all_records(session_id))
    data = df.to_csv(index=False).encode("utf-8")
    return StreamingResponse(io.BytesIO(data), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_{datetime.now().strftime('%Y%m%d')}.csv"})