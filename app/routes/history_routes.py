"""History/Logs and Restore routes.

History: paginated, filterable list of BackupLog rows with a detail view.
Restore: passive & safe — list archives at a destination (JSON), then
download + extract into a user-specified target directory.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_api_auth, require_login
from app.database import get_db
from app.services import (
    destination_service,
    job_service,
    log_service,
    restore_service,
)
from app.templating import templates

router = APIRouter()


def _redirect(path: str, **params) -> RedirectResponse:
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(url=path, status_code=303)


# --- History / Logs ---------------------------------------------------------


@router.get("/history", response_class=HTMLResponse, name="history", response_model=None)
async def history_page(
    request: Request,
    action: str = Query(default=""),
    status: str = Query(default=""),
    page: int = Query(default=1),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the paginated, filterable history of backup/restore logs."""
    guard = require_login(request)
    if guard is not None:
        return guard

    result = log_service.list_logs(
        db,
        action=action or None,
        status=status or None,
        page=page,
    )
    counts = log_service.summary_counts(db)

    rows = [
        {"log": log, "detail": log_service.parse_detail(log)}
        for log in result["items"]
    ]

    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "active_page": "history",
            "page_title": "History / Logs",
            "page_subtitle": "Riwayat eksekusi backup & restore.",
            "rows": rows,
            "pagination": result,
            "counts": counts,
            "filter_action": action,
            "filter_status": status,
        },
    )


# --- Background jobs (realtime monitoring) ----------------------------------


@router.get("/api/jobs/active", response_model=None)
async def jobs_active(
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth),
) -> JSONResponse:
    """Return queued/running backup jobs for realtime monitoring."""
    return JSONResponse({"jobs": job_service.list_active(db)})


@router.get("/api/jobs/{job_id}", response_model=None)
async def job_detail(
    job_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth),
) -> JSONResponse:
    """Return a single job's status/progress."""
    job = job_service.get(db, job_id)
    if job is None:
        return JSONResponse({"error": "Job tidak ditemukan."}, status_code=404)
    return JSONResponse({"job": job})


# --- Restore ----------------------------------------------------------------


@router.get("/restore", response_class=HTMLResponse, name="restore", response_model=None)
async def restore_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the restore page (select destination, list archives, extract)."""
    guard = require_login(request)
    if guard is not None:
        return guard

    destinations = destination_service.list_destinations(db)

    return templates.TemplateResponse(
        request,
        "restore.html",
        {
            "active_page": "restore",
            "page_title": "Restore",
            "page_subtitle": "Pulihkan data dari arsip backup (download & extract).",
            "destinations": destinations,
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
        },
    )


@router.get("/api/restore/archives", response_model=None)
async def restore_archives(
    destination_id: int = Query(...),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth),
) -> JSONResponse:
    """List archives available at the given destination (JSON)."""
    ok, entries, error = restore_service.list_archives(db, destination_id)
    return JSONResponse(
        {"ok": ok, "entries": entries, "error": error}
    )


@router.post("/restore/run", name="restore_run", response_model=None)
async def restore_run(
    request: Request,
    destination_id: int = Form(...),
    archive_ref: str = Form(...),
    archive_name: str = Form(""),
    target_dir: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Execute a restore: download the selected archive and extract it."""
    guard = require_login(request)
    if guard is not None:
        return guard

    result = restore_service.run_restore(
        destination_id, archive_ref, archive_name, target_dir
    )
    flash_type = "success" if result.get("ok") else "error"
    return _redirect("/restore", msg=result.get("message", "Restore selesai."), type=flash_type)
