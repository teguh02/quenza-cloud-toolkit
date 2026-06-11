"""Shared Jinja2 templates instance.

Centralizes template configuration so all routers render with the same
environment and global context.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import __version__

# templates/ lives at the project root (one level above the app package).
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Globals available to every template.
templates.env.globals["app_name"] = "Quenza Cloud Toolkit"
templates.env.globals["app_version"] = __version__


def _localtime_filter(value, fmt: str = "%Y-%m-%d %H:%M"):
    """Jinja filter: convert a UTC datetime to the configured local tz.

    Usage in templates:  {{ log.created_at | localtime }}
    Returns "-" for None.
    """
    if value is None:
        return "-"
    try:
        from app.services import settings_service

        local = settings_service.to_local(value)
        return local.strftime(fmt) if local else "-"
    except Exception:
        try:
            return value.strftime(fmt)
        except Exception:
            return "-"


templates.env.filters["localtime"] = _localtime_filter
