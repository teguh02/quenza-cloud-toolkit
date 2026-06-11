"""Settings routes: timezone and notification configuration."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.services import crypto, notification_service, settings_service
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
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
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
