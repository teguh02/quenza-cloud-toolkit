"""Quenza Cloud Toolkit - FastAPI application entry point.

Phase 1 wires up:
  * Session middleware (signed cookies via SECRET_KEY)
  * Static file serving (/static)
  * Database bootstrap on startup
  * Authentication routes (login/logout) and a protected root page
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.config import settings
from app.database import init_db
from app.routes import (
    auth_routes,
    destination_routes,
    filemanager_routes,
    history_routes,
    page_routes,
    project_routes,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quenza")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run startup/shutdown tasks."""
    if not settings.is_configured:
        logger.warning(
            "App is NOT fully configured. Set MASTER_PASSWORD_HASH and "
            "SECRET_KEY in your .env file (see .env.example)."
        )
    try:
        init_db()
        logger.info("Database initialized at %s", settings.database_url)
    except Exception:  # pragma: no cover - defensive startup guard
        logger.exception("Failed to initialize the database.")
        raise

    # Start the in-process backup scheduler (Phase 4).
    try:
        from app import scheduler

        scheduler.start()
    except Exception:  # pragma: no cover - scheduler must not block startup
        logger.exception("Failed to start the scheduler.")

    yield

    # Shutdown.
    try:
        from app import scheduler

        scheduler.shutdown()
    except Exception:  # pragma: no cover
        pass


app = FastAPI(
    title="Quenza Cloud Toolkit",
    version=__version__,
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# Signed session cookie. https_only is enabled when DEBUG is false.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=not settings.debug,
)

# Static assets (CSS/JS). Created during Phase 1.
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Routers
app.include_router(auth_routes.router)
app.include_router(project_routes.router)
app.include_router(destination_routes.router)
app.include_router(history_routes.router)
app.include_router(filemanager_routes.router)
app.include_router(page_routes.router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Lightweight health check."""
    return {"status": "ok", "version": __version__}


@app.exception_handler(404)
async def not_found_handler(request: Request, _exc) -> RedirectResponse:
    """Send unknown paths to a sensible place.

    Authenticated users go to the dashboard; others to the login page.
    """
    from app.auth import is_authenticated

    target = "/" if is_authenticated(request) else "/login"
    return RedirectResponse(url=target, status_code=303)
