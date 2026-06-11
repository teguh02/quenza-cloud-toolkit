"""Destination routes: list, create, update, delete, and test connection."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.services import destination_service
from app.services.destinations import list_adapter_specs
from app.templating import templates

router = APIRouter(prefix="/destinations")


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
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
        },
    )


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
