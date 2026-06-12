"""File manager API: JSON endpoints for browsing the server filesystem.

Consumed by the Integrated File Manager UI on the project detail page.
All endpoints require an authenticated session (HTTP 401 otherwise).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

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


class MkdirRequest(BaseModel):
    path: str
    name: str

class MkfileRequest(BaseModel):
    path: str
    name: str

class EditRequest(BaseModel):
    path: str
    content: str

class DeleteRequest(BaseModel):
    path: str

@router.post("/mkdir")
async def mkdir(req: MkdirRequest) -> dict:
    return filemanager_service.create_folder(req.path, req.name)

@router.post("/mkfile")
async def mkfile(req: MkfileRequest) -> dict:
    return filemanager_service.create_file(req.path, req.name)

@router.get("/read")
async def read_file(path: str = Query(...)) -> dict:
    return filemanager_service.read_file_content(path)

@router.post("/edit")
async def edit_file(req: EditRequest) -> dict:
    return filemanager_service.write_file_content(req.path, req.content)

@router.post("/delete")
async def delete_item(req: DeleteRequest) -> dict:
    return filemanager_service.delete_target(req.path)
