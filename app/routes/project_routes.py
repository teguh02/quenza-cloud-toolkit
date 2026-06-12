"""Project routes: list, create, detail, update, delete, and source management.

Server-side rendered (Jinja2) to match the app's frontend strategy.
Mutations use POST + redirect (PRG pattern); user feedback is carried via
flash-style query parameters that templates render as Quenza toasts.
"""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_api_auth, require_login
from app.database import get_db
from app.models import SourceType
from app.services import (
    destination_service,
    job_service,
    project_service,
    schedule_service,
    source_size_service,
)
from app.templating import templates

router = APIRouter(prefix="/projects")


def _redirect(path: str, **params) -> RedirectResponse:
    """Build a 303 redirect with optional flash query params."""
    if params:
        path = f"{path}?{urlencode(params)}"
    return RedirectResponse(url=path, status_code=303)


@router.get("", response_class=HTMLResponse, name="projects", response_model=None)
async def projects_list(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """List all projects as a card grid."""
    guard = require_login(request)
    if guard is not None:
        return guard

    projects = project_service.list_projects(db)
    # Precompute source counts for the cards.
    cards = [
        {
            "project": p,
            "source_count": project_service.count_sources(db, p.id),
        }
        for p in projects
    ]

    return templates.TemplateResponse(
        request,
        "projects/list.html",
        {
            "active_page": "projects",
            "page_title": "Projects",
            "page_subtitle": "Kelola workspace backup Anda.",
            "cards": cards,
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
        },
    )


@router.post("/create", name="projects_create", response_model=None)
async def projects_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    archive_format: str = Form("zip"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Create a new project."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        project = project_service.create_project(
            db, name=name, description=description, archive_format=archive_format
        )
    except ValueError as exc:
        return _redirect("/projects", msg=str(exc), type="error")

    return _redirect(f"/projects/{project.id}", msg="Project berhasil dibuat.")


@router.get("/{project_id}", response_class=HTMLResponse, name="project_detail", response_model=None)
async def project_detail(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the detail view for a single project."""
    guard = require_login(request)
    if guard is not None:
        return guard

    project = project_service.get_project(db, project_id)
    if project is None:
        return _redirect("/projects", msg="Project tidak ditemukan.", type="error")

    sources = [
        {"source": s, "meta": project_service.source_type_meta(s)}
        for s in project.sources
    ]

    all_destinations = destination_service.list_destinations(db)
    selected_ids = {d.id for d in project.destinations}
    schedule = project.schedule

    # Fetch Docker hosts for source addition
    from app.services import docker_service
    docker_hosts = docker_service.get_hosts(db)

    # Total size of backup sources (cached; recomputed in background if stale).
    size_entry = source_size_service.ensure_fresh(db, project_id)

    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {
            "active_page": "projects",
            "page_title": project.name,
            "page_subtitle": "Detail & konfigurasi project.",
            "project": project,
            "sources": sources,
            "size_entry": size_entry,
            "all_destinations": all_destinations,
            "docker_hosts": docker_hosts,
            "selected_dest_ids": selected_ids,
            "schedule": schedule,
            "schedule_desc": schedule_service.describe(schedule),
            "flash": request.query_params.get("msg"),
            "flash_type": request.query_params.get("type", "success"),
        },
    )


# --- Backup-source total size (background-computed, cached) ------------------


@router.get("/{project_id}/sources/size", response_model=None)
async def project_sources_size(
    project_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth),
) -> JSONResponse:
    """Return the cached size entry for a project's backup sources (JSON).

    Kicks off a background recompute if the cache is stale, so the client can
    poll this endpoint until ``status == 'done'``.
    """
    if project_service.get_project(db, project_id) is None:
        return JSONResponse({"error": "Project tidak ditemukan."}, status_code=404)
    entry = source_size_service.ensure_fresh(db, project_id)
    return JSONResponse(entry)


@router.post("/{project_id}/sources/size/recompute", response_model=None)
async def project_sources_size_recompute(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth),
) -> JSONResponse:
    """Force a background recompute of a project's backup-source size."""
    if project_service.get_project(db, project_id) is None:
        return JSONResponse({"error": "Project tidak ditemukan."}, status_code=404)
    try:
        source_size_service.enqueue_compute(project_id, force=True)
    except Exception as exc:  # pragma: no cover - defensive
        return JSONResponse({"error": f"Gagal menjadwalkan: {exc}"}, status_code=500)
    entry = source_size_service.get_cached(db, project_id)
    return JSONResponse(entry)


@router.post("/{project_id}/update", name="project_update", response_model=None)
async def project_update(
    request: Request,
    project_id: int,
    description: str = Form(""),
    archive_format: str = Form("zip"),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Update project metadata and output format."""
    guard = require_login(request)
    if guard is not None:
        return guard

    try:
        project_service.update_project(
            db,
            project_id,
            description=description,
            archive_format=archive_format,
        )
    except ValueError as exc:
        return _redirect(f"/projects/{project_id}", msg=str(exc), type="error")

    return _redirect(f"/projects/{project_id}", msg="Project diperbarui.")


@router.post("/{project_id}/delete", name="project_delete", response_model=None)
async def project_delete(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Delete a project and its sources."""
    guard = require_login(request)
    if guard is not None:
        return guard

    deleted = project_service.delete_project(db, project_id)
    if not deleted:
        return _redirect("/projects", msg="Project tidak ditemukan.", type="error")
    return _redirect("/projects", msg="Project dihapus.")


# --- Source management ------------------------------------------------------


@router.post("/{project_id}/sources/add", name="source_add", response_model=None)
async def source_add(
    request: Request,
    project_id: int,
    source_type: str = Form(...),
    label: str = Form(""),
    path: str = Form(""),
    db_host: str = Form(""),
    db_port: str = Form(""),
    db_name: str = Form(""),
    db_user: str = Form(""),
    db_password: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Attach a backup source (directory/file/mysql/postgres) to a project."""
    guard = require_login(request)
    if guard is not None:
        return guard

    # Parse optional port.
    port: int | None = None
    if db_port.strip():
        try:
            port = int(db_port.strip())
        except ValueError:
            return _redirect(
                f"/projects/{project_id}", msg="Port database harus angka.", type="error"
            )

    try:
        project_service.add_source(
            db,
            project_id,
            source_type=source_type,
            label=label,
            path=path,
            db_host=db_host,
            db_port=port,
            db_name=db_name,
            db_user=db_user,
            db_password=db_password,
        )
    except ValueError as exc:
        return _redirect(f"/projects/{project_id}", msg=str(exc), type="error")

    return _redirect(f"/projects/{project_id}", msg="Sumber backup ditambahkan.")


@router.post(
    "/{project_id}/sources/add-paths", name="source_add_paths", response_model=None
)
async def source_add_paths(
    request: Request,
    project_id: int,
    paths: list[str] = Form(default=[]),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Bulk-add filesystem sources selected via the File Manager.

    Each path is auto-classified as directory or file based on the
    filesystem; non-existent paths are skipped.
    """
    guard = require_login(request)
    if guard is not None:
        return guard

    from app.services import filemanager_service

    added = 0
    skipped = 0
    for raw in paths:
        raw = (raw or "").strip()
        if not raw:
            continue
        exists, is_dir = filemanager_service.path_exists(raw)
        if not exists:
            skipped += 1
            continue
        stype = SourceType.DIRECTORY.value if is_dir else SourceType.FILE.value
        try:
            project_service.add_source(
                db, project_id, source_type=stype, path=raw
            )
            added += 1
        except ValueError:
            skipped += 1

    if added == 0 and skipped == 0:
        return _redirect(
            f"/projects/{project_id}", msg="Tidak ada path yang dipilih.", type="error"
        )

    msg = f"{added} sumber ditambahkan."
    if skipped:
        msg += f" {skipped} dilewati (tidak valid)."
    return _redirect(f"/projects/{project_id}", msg=msg)


@router.post(
    "/{project_id}/sources/{source_id}/delete",
    name="source_delete",
    response_model=None,
)
async def source_delete(
    request: Request,
    project_id: int,
    source_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Remove a source from a project."""
    guard = require_login(request)
    if guard is not None:
        return guard

    deleted = project_service.delete_source(db, project_id, source_id)
    if not deleted:
        return _redirect(
            f"/projects/{project_id}", msg="Sumber tidak ditemukan.", type="error"
        )
    return _redirect(f"/projects/{project_id}", msg="Sumber dihapus.")


@router.post(
    "/{project_id}/sources/{source_id}/test",
    name="source_test",
    response_model=None,
)
async def source_test(
    request: Request,
    project_id: int,
    source_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Test connection for a database source."""
    guard = require_login(request)
    if guard is not None:
        return JSONResponse({"success": False, "message": "Unauthorized"}, status_code=401)

    project = project_service.get_project(db, project_id)
    if not project:
        return JSONResponse({"success": False, "message": "Project tidak ditemukan."}, status_code=404)

    source = next((s for s in project.sources if s.id == source_id), None)
    if not source:
        return JSONResponse({"success": False, "message": "Sumber tidak ditemukan."}, status_code=404)

    if source.source_type.value not in ["mysql", "postgres"]:
        return JSONResponse({"success": False, "message": "Tipe sumber tidak didukung untuk tes."}, status_code=400)

    from app.services import db_dump_service, crypto
    
    password = source.db_password
    if password and password.startswith("gAAAAA"):
        password = crypto.decrypt_secret(password) or ""

    if source.source_type.value == "mysql":
        ok, msg = db_dump_service.test_mysql_connection(
            host=source.db_host,
            port=source.db_port,
            name=source.db_name,
            user=source.db_user,
            password=password,
        )
    else:
        ok, msg = db_dump_service.test_postgres_connection(
            host=source.db_host,
            port=source.db_port,
            name=source.db_name,
            user=source.db_user,
            password=password,
        )

    return JSONResponse({"success": ok, "message": msg})


# --- Destinations linking, scheduling, and backup run (Phase 4) -------------


@router.post("/{project_id}/destinations", name="project_set_destinations", response_model=None)
async def project_set_destinations(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Set the selective destinations targeted by this project."""
    guard = require_login(request)
    if guard is not None:
        return guard

    form = await request.form()
    raw_ids = form.getlist("destination_ids")
    ids: list[int] = []
    for r in raw_ids:
        try:
            ids.append(int(r))
        except (TypeError, ValueError):
            continue

    try:
        schedule_service.set_project_destinations(db, project_id, ids)
    except ValueError as exc:
        return _redirect(f"/projects/{project_id}", msg=str(exc), type="error")

    return _redirect(f"/projects/{project_id}", msg="Destinasi project diperbarui.")


@router.post("/{project_id}/schedule", name="project_set_schedule", response_model=None)
async def project_set_schedule(
    request: Request,
    project_id: int,
    enabled: str = Form(default=""),
    frequency: str = Form("daily"),
    hour: str = Form("2"),
    minute: str = Form("0"),
    day_of_week: str = Form(default=""),
    day_of_month: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Create/update the project's schedule and sync the scheduler."""
    guard = require_login(request)
    if guard is not None:
        return guard

    def _to_int(value: str, default: int | None = None) -> int | None:
        value = (value or "").strip()
        if not value:
            return default
        try:
            return int(value)
        except ValueError:
            return default

    try:
        schedule_service.set_schedule(
            db,
            project_id,
            enabled=bool(enabled),
            frequency=frequency,
            hour=_to_int(hour, 2) or 0,
            minute=_to_int(minute, 0) or 0,
            day_of_week=_to_int(day_of_week),
            day_of_month=_to_int(day_of_month),
        )
    except ValueError as exc:
        return _redirect(f"/projects/{project_id}", msg=str(exc), type="error")

    # Sync the in-process scheduler (best-effort).
    try:
        from app import scheduler

        scheduler.sync_project(project_id)
    except Exception:  # pragma: no cover - scheduler optional at runtime
        pass

    return _redirect(f"/projects/{project_id}", msg="Jadwal diperbarui.")


@router.post("/{project_id}/run", name="project_run_backup", response_model=None)
async def project_run_backup(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Trigger a manual backup in the BACKGROUND and redirect to History.

    The backup runs off the request/event loop so the UI stays responsive and
    reverse proxies don't time out. Progress is monitored in real time on the
    History page.
    """
    guard = require_login(request)
    if guard is not None:
        return guard

    project = project_service.get_project(db, project_id)
    if project is None:
        return _redirect("/projects", msg="Project tidak ditemukan.", type="error")

    try:
        job_service.enqueue_backup(project_id, trigger="manual")
    except job_service.JobBusyError as exc:
        return _redirect(f"/projects/{project_id}", msg=str(exc), type="error")
    except Exception as exc:  # pragma: no cover - defensive
        return _redirect(
            f"/projects/{project_id}", msg=f"Gagal memulai backup: {exc}", type="error"
        )

    return _redirect(
        "/history",
        msg="Backup dimulai di latar belakang. Pantau prosesnya di sini.",
        type="info",
    )
