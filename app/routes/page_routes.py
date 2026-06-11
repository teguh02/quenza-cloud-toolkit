"""Application page routes: dashboard and sidebar sections.

Phase 2 implements the full Dashboard and renders styled placeholder
pages for the remaining sidebar sections (Projects, Schedules,
Destinations, History/Logs, Settings, Help). These placeholders are
replaced by real functionality in Phases 3-5.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import require_login
from app.database import get_db
from app.services import dashboard_service, schedule_service
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="dashboard", response_model=None)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the main dashboard (stats, trend chart, quick actions, feed)."""
    guard = require_login(request)
    if guard is not None:
        return guard

    trend_7 = dashboard_service.get_backup_trend(db, 7)
    trend_30 = dashboard_service.get_backup_trend(db, 30)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "page_title": "Dashboard",
            "page_subtitle": "Ringkasan aktivitas backup & restore Anda.",
            "stat_cards": dashboard_service.get_stat_cards(db),
            "quick_actions": dashboard_service.get_quick_actions(),
            "activity": dashboard_service.get_recent_activity(db),
            "trend_7": trend_7,
            "trend_30": trend_30,
        },
    )


@router.get("/schedules", response_class=HTMLResponse, name="schedules", response_model=None)
async def schedules_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """List all project schedules."""
    guard = require_login(request)
    if guard is not None:
        return guard

    schedules = schedule_service.list_schedules(db)
    rows = [
        {
            "schedule": s,
            "project": s.project,
            "desc": schedule_service.describe(s),
        }
        for s in schedules
    ]

    return templates.TemplateResponse(
        request,
        "schedules.html",
        {
            "active_page": "schedules",
            "page_title": "Schedules",
            "page_subtitle": "Jadwal backup otomatis per project.",
            "rows": rows,
        },
    )


# --- Sidebar placeholder pages ---------------------------------------------

# (key, path, title, subtitle, icon, tone, fg)
_PLACEHOLDER_PAGES = [
    ("settings", "/settings", "Settings",
     "Konfigurasi aplikasi & preferensi.", "cog", "pastel-blue", "text-blue-500",
     "Pengaturan lanjutan dibangun pada fase berikutnya."),
    ("help", "/help", "Help / Documentation",
     "Panduan penggunaan Quenza Cloud Toolkit.", "help", "pastel-orange", "text-amber-500",
     "Dokumentasi lengkap akan ditambahkan pada fase berikutnya."),
]


def _make_placeholder(key, path, title, subtitle, icon, tone, fg, note):
    """Create and register a guarded placeholder route."""

    @router.get(path, response_class=HTMLResponse, name=key, response_model=None)
    async def _page(request: Request) -> HTMLResponse | RedirectResponse:
        guard = require_login(request)
        if guard is not None:
            return guard
        return templates.TemplateResponse(
            request,
            "placeholder.html",
            {
                "active_page": key,
                "page_title": title,
                "page_subtitle": subtitle,
                "icon": icon,
                "tone": tone,
                "fg": fg,
                "note": note,
            },
        )

    return _page


for _args in _PLACEHOLDER_PAGES:
    _make_placeholder(*_args)
