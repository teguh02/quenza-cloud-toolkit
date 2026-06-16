"""Settings routes: timezone and notification configuration."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.services import (
    av_whitelist_service,
    crypto,
    notification_service,
    scheduler_health_service,
    settings_service,
)
from app.templating import templates

router = APIRouter(prefix="/settings")


def _redirect(path: str, **params) -> RedirectResponse:
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(url=path, status_code=303)


@router.get("", response_class=HTMLResponse, name="settings", response_model=None)
async def settings_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the settings page (timezone + notifications)."""
    guard = require_login(request)
    if guard is not None:
        return guard

    notif = settings_service.get_notification_config()
    scheduler_health = scheduler_health_service.get_health_status(db)
    ai_config = settings_service.get_ai_config()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "page_title": "Settings",
            "page_subtitle": "Konfigurasi zona waktu & notifikasi.",
            "current_tz": settings_service.get_timezone_name(),
            "common_tz": settings_service.COMMON_TIMEZONES,
            "all_tz": settings_service.all_timezones(),
            "notif": notif,
            "max_recipients": settings_service.MAX_RECIPIENTS,
            "crypto_ready": crypto.is_configured(),
            "scheduler_health": scheduler_health,
            "av_whitelist": av_whitelist_service.list_entries(db),
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
            "ai_config": ai_config,
        },
    )


@router.post("/general", name="settings_general", response_model=None)
async def settings_general(
    request: Request,
    timezone: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Save the global timezone and resync the scheduler."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        settings_service.set_timezone(db, timezone)
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")

    # Re-evaluate schedules under the new timezone.
    try:
        from app import scheduler

        scheduler.reload_jobs()
    except Exception:  # pragma: no cover
        pass

    return _redirect("/settings", msg="Zona waktu disimpan.")


@router.post("/ai", name="settings_ai", response_model=None)
async def settings_ai(
    request: Request,
    ai_api_key: str = Form(""),
    ai_enabled: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Save the AI configuration."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        settings_service.save_ai_config(
            db=db,
            api_key=ai_api_key,
            enabled=bool(ai_enabled),
        )
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")

    return _redirect("/settings", msg="Pengaturan AI disimpan.")


@router.post("/notifications", name="settings_notifications", response_model=None)
async def settings_notifications(
    request: Request,
    channel: str = Form("none"),
    notify_on: str = Form("all"),
    smtp_host: str = Form(""),
    smtp_port: str = Form("587"),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    smtp_from: str = Form(""),
    smtp_use_tls: str = Form(""),
    recipients_raw: str = Form(""),
    telegram_token: str = Form(""),
    telegram_chat_id: str = Form(""),
    notify_on_backup: str = Form(""),
    notify_on_scan: str = Form(""),
    notify_on_disk: str = Form(""),
    notify_on_health: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Save notification settings."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        settings_service.save_notifications(
            db,
            channel=channel,
            notify_on=notify_on,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            smtp_from=smtp_from,
            smtp_use_tls=bool(smtp_use_tls),
            recipients_raw=recipients_raw,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            notify_on_backup=bool(notify_on_backup),
            notify_on_scan=bool(notify_on_scan),
            notify_on_disk=bool(notify_on_disk),
            notify_on_health=bool(notify_on_health),
        )
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")

    return _redirect("/settings", msg="Pengaturan notifikasi disimpan.")


@router.post("/notifications/test", name="settings_notifications_test", response_model=None)
async def settings_notifications_test(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Send a test notification via the active channel."""
    guard = require_login(request)
    if guard is not None:
        return guard

    ok, message = notification_service.send_test()
    return _redirect("/settings", msg=message, type="success" if ok else "error")


@router.post("/antivirus-whitelist/add", name="settings_av_whitelist_add", response_model=None)
async def settings_av_whitelist_add(
    request: Request,
    file_name: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Add new Antivirus whitelist filename."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        av_whitelist_service.create_entry(db, file_name)
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")
    return _redirect("/settings", msg="Daftar putih berhasil ditambahkan.")


@router.post(
    "/antivirus-whitelist/{entry_id}/edit",
    name="settings_av_whitelist_edit",
    response_model=None,
)
async def settings_av_whitelist_edit(
    request: Request,
    entry_id: int,
    file_name: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update Antivirus whitelist filename."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        av_whitelist_service.update_entry(db, entry_id, file_name)
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")
    return _redirect("/settings", msg="Daftar putih berhasil diperbarui.")


@router.post(
    "/antivirus-whitelist/{entry_id}/delete",
    name="settings_av_whitelist_delete",
    response_model=None,
)
async def settings_av_whitelist_delete(
    request: Request,
    entry_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete Antivirus whitelist filename."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        av_whitelist_service.delete_entry(db, entry_id)
    except ValueError as exc:
        return _redirect("/settings", msg=str(exc), type="error")
    return _redirect("/settings", msg="Daftar putih berhasil dihapus.")


@router.get("/api/check-update", name="settings_check_update", response_model=None)
async def settings_check_update(request: Request):
    """Check for toolkit updates via background AJAX."""
    guard = require_login(request)
    if guard is not None:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "unauthorized"}, status_code=401)
        
    try:
        import toolkit
        status = toolkit.check_update(verbose=False)
        return status
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": str(exc)}, status_code=500)
