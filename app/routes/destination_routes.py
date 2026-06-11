"""Destination routes: list, create, update, delete, test, and Drive OAuth."""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.config import settings
from app.database import get_db
from app.services import crypto, destination_service, gdrive_oauth
from app.services.destinations import list_adapter_specs
from app.templating import templates

router = APIRouter(prefix="/destinations")

_GDRIVE_STATE_KEY = "gdrive_oauth_state"
_GDRIVE_NAME_KEY = "gdrive_oauth_name"
_GDRIVE_FOLDER_KEY = "gdrive_oauth_folder"


def _redirect(path: str, **params) -> RedirectResponse:
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(url=path, status_code=303)


@router.get("", response_class=HTMLResponse, name="destinations", response_model=None)
async def destinations_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """List all destinations and provide create/edit modals."""
    guard = require_login(request)
    if guard is not None:
        return guard

    destinations = destination_service.list_destinations(db)
    cards = [
        {"dest": d, "summary": destination_service.display_summary(d)}
        for d in destinations
    ]

    return templates.TemplateResponse(
        request,
        "destinations.html",
        {
            "active_page": "destinations",
            "page_title": "Destinations",
            "page_subtitle": "Kelola tujuan penyimpanan backup.",
            "cards": cards,
            "specs": list_adapter_specs(),
            "gdrive_ready": settings.google_oauth_ready and crypto.is_configured(),
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
        },
    )


# --- Google Drive OAuth -----------------------------------------------------


@router.get("/gdrive/connect", name="gdrive_connect", response_model=None)
async def gdrive_connect(
    request: Request,
    name: str = Query(default=""),
    folder_id: str = Query(default=""),
) -> RedirectResponse:
    """Begin the Google Drive OAuth consent flow."""
    guard = require_login(request)
    if guard is not None:
        return guard

    if not crypto.is_configured():
        return _redirect(
            "/destinations",
            msg="ENCRYPTION_KEY belum diatur (python generate_key.py).",
            type="error",
        )

    state = secrets.token_urlsafe(24)
    request.session[_GDRIVE_STATE_KEY] = state
    request.session[_GDRIVE_NAME_KEY] = (name or "").strip()
    request.session[_GDRIVE_FOLDER_KEY] = (folder_id or "").strip()

    try:
        auth_url = gdrive_oauth.build_auth_url(state)
    except gdrive_oauth.OAuthError as exc:
        return _redirect("/destinations", msg=str(exc), type="error")

    return RedirectResponse(url=auth_url, status_code=303)


@router.get("/gdrive/callback", name="gdrive_callback", response_model=None)
async def gdrive_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str = Query(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Handle the OAuth redirect: verify state, exchange code, save dest."""
    guard = require_login(request)
    if guard is not None:
        return guard

    if error:
        return _redirect("/destinations", msg=f"Koneksi dibatalkan: {error}", type="error")

    expected = request.session.pop(_GDRIVE_STATE_KEY, None)
    saved_name = request.session.pop(_GDRIVE_NAME_KEY, "")
    saved_folder = request.session.pop(_GDRIVE_FOLDER_KEY, "")

    if not expected or state != expected:
        return _redirect(
            "/destinations", msg="State OAuth tidak valid (coba ulangi).", type="error"
        )

    try:
        account = gdrive_oauth.exchange_code(code, state=state)
    except gdrive_oauth.OAuthError as exc:
        return _redirect("/destinations", msg=str(exc), type="error")

    # Auto-create a Drive folder when the user left Folder ID empty, so
    # backups land in a tidy dedicated folder. Failure is non-fatal.
    folder_id = saved_folder
    auto_created = False
    if not folder_id:
        from app.services.destinations import gdrive_adapter

        folder_label = (saved_name or "").strip() or f"Quenza Backups - {account.email}"
        new_id = gdrive_adapter.create_folder_with_token(
            account.refresh_token, folder_label
        )
        if new_id:
            folder_id = new_id
            auto_created = True

    try:
        destination_service.create_gdrive_destination(
            db,
            name=saved_name or account.email,
            refresh_token=account.refresh_token,
            email=account.email,
            folder_id=folder_id,
        )
    except ValueError as exc:
        return _redirect("/destinations", msg=str(exc), type="error")

    label = account.email or "akun Google"
    msg = f"Google Drive terhubung: {label}."
    if auto_created:
        msg += " Folder backup otomatis dibuat."
    return _redirect("/destinations", msg=msg)


@router.post("/create", name="destination_create", response_model=None)
async def destination_create(
    request: Request,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Create a destination from posted form data."""
    guard = require_login(request)
    if guard is not None:
        return guard

    form = dict(await request.form())
    name = form.get("name", "")
    dest_type = form.get("dest_type", "")

    try:
        destination_service.create_destination(
            db, name=name, dest_type=dest_type, form=form
        )
    except ValueError as exc:
        return _redirect("/destinations", msg=str(exc), type="error")

    return _redirect("/destinations", msg="Destinasi berhasil dibuat.")


@router.post("/{dest_id}/update", name="destination_update", response_model=None)
async def destination_update(
    request: Request,
    dest_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update a destination."""
    guard = require_login(request)
    if guard is not None:
        return guard

    form = dict(await request.form())
    name = form.get("name", "")

    try:
        destination_service.update_destination(db, dest_id, name=name, form=form)
    except ValueError as exc:
        return _redirect("/destinations", msg=str(exc), type="error")

    return _redirect("/destinations", msg="Destinasi diperbarui.")


@router.post("/{dest_id}/delete", name="destination_delete", response_model=None)
async def destination_delete(
    request: Request,
    dest_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete a destination."""
    guard = require_login(request)
    if guard is not None:
        return guard

    ok = destination_service.delete_destination(db, dest_id)
    if not ok:
        return _redirect("/destinations", msg="Destinasi tidak ditemukan.", type="error")
    return _redirect("/destinations", msg="Destinasi dihapus.")


@router.post("/{dest_id}/test", name="destination_test", response_model=None)
async def destination_test(
    request: Request,
    dest_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Test a destination's connectivity."""
    guard = require_login(request)
    if guard is not None:
        return guard

    ok, message = destination_service.test_destination(db, dest_id)
    return _redirect(
        "/destinations", msg=message, type="success" if ok else "error"
    )
