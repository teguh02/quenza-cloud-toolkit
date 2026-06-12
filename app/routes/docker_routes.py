"""Routes for Docker Management."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_api_auth, require_login
from app.database import get_db
from app.services import docker_service
from app.templating import templates

router = APIRouter()

@router.get("/docker", response_class=HTMLResponse, name="docker", response_model=None)
async def docker_page(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    """Render the main Docker management dashboard."""
    guard = require_login(request)
    if guard is not None:
        return guard

    docker_service.ensure_default_host(db)
    status = docker_service.check_docker_status()
    hosts = docker_service.get_hosts(db)

    return templates.TemplateResponse(
        request,
        "docker.html",
        {
            "active_page": "docker",
            "page_title": "Docker Management",
            "page_subtitle": "Kelola kontainer, images, volumes, dan networks Docker.",
            "docker_status": status,
            "hosts": hosts,
        },
    )

@router.get("/api/docker/{host_id}/containers")
async def api_get_containers(
    host_id: int, 
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    return docker_service.list_containers(db, host_id)

@router.get("/api/docker/{host_id}/images")
async def api_get_images(
    host_id: int, 
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    return docker_service.list_images(db, host_id)

@router.get("/api/docker/{host_id}/volumes")
async def api_get_volumes(
    host_id: int, 
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    return docker_service.list_volumes(db, host_id)

@router.get("/api/docker/{host_id}/networks")
async def api_get_networks(
    host_id: int, 
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    return docker_service.list_networks(db, host_id)

class ContainerActionRequest(BaseModel):
    action: str

@router.post("/api/docker/{host_id}/containers/{container_id}/action")
async def api_container_action(
    host_id: int,
    container_id: str,
    req: ContainerActionRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    return docker_service.container_action(db, host_id, container_id, req.action)

class ResourceActionRequest(BaseModel):
    resource_id: str

@router.post("/api/docker/{host_id}/{resource_type}/remove")
async def api_remove_resource(
    host_id: int,
    resource_type: str,
    req: ResourceActionRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_auth)
):
    # Remove trailing 's' to match service layer expected 'image', 'volume', 'network'
    rtype = resource_type[:-1] if resource_type.endswith('s') else resource_type
    return docker_service.remove_resource(db, host_id, rtype, req.resource_id)
