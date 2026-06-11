"""Authentication routes: login and logout."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth import (
    is_authenticated,
    login_session,
    logout_session,
    verify_password,
)
from app.templating import templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="login", response_model=None)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    """Render the login page, or redirect to dashboard if already in."""
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None},
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit", response_model=None)
async def login_submit(
    request: Request,
    master_password: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    """Validate the Master Password and start a session on success."""
    if verify_password(master_password):
        login_session(request)
        return RedirectResponse(url="/", status_code=303)

    # Failed attempt: re-render with a Quenza-styled error state.
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": "Master Password salah. Silakan coba lagi."},
        status_code=401,
    )


@router.get("/logout", name="logout")
async def logout(request: Request) -> RedirectResponse:
    """Clear the session and return to the login page."""
    logout_session(request)
    return RedirectResponse(url="/login", status_code=303)
