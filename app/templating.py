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
