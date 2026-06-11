"""Authentication helpers: bcrypt verification and login guards."""

import bcrypt
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import settings

SESSION_AUTH_KEY = "authenticated"


def verify_password(plain_password: str) -> bool:
    """Verify a plaintext password against the configured bcrypt hash.

    Returns False on any error (missing hash, malformed hash, mismatch)
    so authentication never raises to the request handler.
    """
    stored_hash = settings.master_password_hash
    if not stored_hash or not plain_password:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            stored_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Malformed hash in .env or invalid encoding.
        return False


def is_authenticated(request: Request) -> bool:
    """Return True if the current session is authenticated."""
    try:
        return bool(request.session.get(SESSION_AUTH_KEY, False))
    except (AssertionError, AttributeError):
        # SessionMiddleware not installed / session unavailable.
        return False


def login_session(request: Request) -> None:
    """Mark the current session as authenticated."""
    request.session[SESSION_AUTH_KEY] = True


def logout_session(request: Request) -> None:
    """Clear authentication from the current session."""
    request.session.clear()


def require_login(request: Request) -> RedirectResponse | None:
    """Dependency-style guard.

    Returns a RedirectResponse to /login when not authenticated, otherwise
    None. Route handlers should check the return value and return it early.
    """
    if not is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


def require_api_auth(request: Request) -> None:
    """FastAPI dependency for JSON API endpoints.

    Raises HTTP 401 when the session is not authenticated so the frontend
    fetch layer can react, rather than receiving an HTML redirect.
    """
    if not is_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
