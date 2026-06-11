"""File manager API: JSON endpoints for browsing the server filesystem.

Consumed by the Integrated File Manager UI on the project detail page.
All endpoints require an authenticated session (HTTP 401 otherwise).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import require_api_auth
from app.services import filemanager_service

router = APIRouter(prefix="/api/fs", dependencies=[Depends(require_api_auth)])


@router.get("/browse")
async def browse(
    path: str | None = Query(default=None),
    show_hidden: bool = Query(default=False),
) -> dict:
    """Return a directory listing for the given path.

    When `path` is omitted, returns the virtual root (drives on Windows,
    "/" on POSIX). Errors are returned as a structured payload with
    ok=False rather than raising.
    """
    return filemanager_service.browse(path, show_hidden=show_hidden)


@router.get("/check")
async def check(path: str = Query(...)) -> dict:
    """Check whether a path exists and whether it is a directory."""
    exists, is_dir = filemanager_service.path_exists(path)
    return {"exists": exists, "is_dir": is_dir, "path": path}
