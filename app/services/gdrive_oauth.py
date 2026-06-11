"""Google Drive OAuth helper (web server flow).

Builds the consent URL and exchanges the authorization code for a
refresh token, then resolves the account email. Uses google-auth-oauthlib
(Flow). All functions raise OAuthError for predictable failures so routes
can show a friendly message.

Scope: drive.file — the app may only see/manage files it created. This is
the safest scope and avoids Google's strict verification for broad access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Relax oauthlib scope validation. Google may grant a slightly different set
# of scopes than requested (e.g. it adds userinfo.profile/openid). Without
# this, fetch_token() raises "Scope has changed". Must be set before any
# oauthlib import/usage, so we set it at module import time.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
# Allow http redirect URIs for local development (127.0.0.1).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from app.config import settings

# drive.file: per-file access to files created by this app.
# Google often returns extra related scopes (e.g. userinfo.profile) even when
# not explicitly requested, depending on the consent screen configuration.
# We include them here and also relax scope validation below so the token
# exchange does not fail with "Scope has changed".
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


class OAuthError(RuntimeError):
    """Raised for OAuth configuration or exchange failures."""


@dataclass
class ConnectedAccount:
    """Result of a successful OAuth exchange."""

    refresh_token: str
    email: str


def _client_config() -> dict:
    """Build the google-auth client config from settings."""
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def build_auth_url(state: str) -> str:
    """Return the Google consent URL.

    Args:
        state: anti-CSRF token stored in the session and verified on callback.

    Raises:
        OAuthError: if OAuth is not configured or the SDK is missing.
    """
    if not settings.google_oauth_ready:
        raise OAuthError(
            "Google OAuth belum dikonfigurasi. Atur GOOGLE_CLIENT_ID, "
            "GOOGLE_CLIENT_SECRET, dan GOOGLE_REDIRECT_URI di .env."
        )
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover
        raise OAuthError(
            "Library 'google-auth-oauthlib' belum terpasang."
        ) from exc

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",       # request a refresh token
        include_granted_scopes="true",
        prompt="consent",            # force refresh_token on re-consent
        state=state,
    )
    return auth_url


def exchange_code(code: str, state: str | None = None) -> ConnectedAccount:
    """Exchange an authorization code for a refresh token + account email.

    Raises:
        OAuthError: on any failure (missing config, no refresh token, etc.).
    """
    if not settings.google_oauth_ready:
        raise OAuthError("Google OAuth belum dikonfigurasi.")
    if not code:
        raise OAuthError("Authorization code kosong.")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:  # pragma: no cover
        raise OAuthError("Library 'google-auth-oauthlib' belum terpasang.") from exc

    # Belt-and-suspenders: ensure scope relaxation is active for this exchange.
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

    # Passing scopes=None avoids oauthlib validating the granted scopes
    # against a fixed list (Google may return extra related scopes).
    flow = Flow.from_client_config(_client_config(), scopes=None, state=state)
    flow.redirect_uri = settings.google_redirect_uri

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        raise OAuthError(f"Gagal menukar kode OAuth: {exc}") from exc

    creds = flow.credentials
    refresh_token = getattr(creds, "refresh_token", None)
    if not refresh_token:
        raise OAuthError(
            "Tidak menerima refresh token. Coba cabut akses aplikasi di "
            "akun Google lalu connect ulang."
        )

    email = _resolve_email(creds)
    return ConnectedAccount(refresh_token=refresh_token, email=email)


def _resolve_email(creds) -> str:
    """Best-effort resolution of the account email."""
    # Try the OpenID id_token first (no extra HTTP call).
    try:
        from google.oauth2 import id_token  # type: ignore
        from google.auth.transport import requests as grequests  # type: ignore

        if getattr(creds, "id_token", None):
            info = id_token.verify_oauth2_token(
                creds.id_token, grequests.Request(), settings.google_client_id
            )
            if info.get("email"):
                return info["email"]
    except Exception:  # pragma: no cover - fall through to API call
        pass

    # Fallback: call the userinfo endpoint.
    try:
        from googleapiclient.discovery import build

        service = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = service.userinfo().get().execute()
        return info.get("email", "")
    except Exception:  # pragma: no cover
        return ""
