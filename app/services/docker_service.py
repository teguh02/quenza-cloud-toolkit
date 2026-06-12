"""Docker management service."""

import json
import shutil
from typing import Any

from sqlalchemy.orm import Session
from app.models import DockerHost
from app.services import crypto

# Note: The docker module might not be installed in all environments.
# We wrap it in a try-except or just import it and let the exception bubble up
# since it's now in requirements.txt.
import docker


def check_docker_status() -> dict[str, Any]:
    """Check if docker is installed and daemon is running."""
    is_installed = shutil.which("docker") is not None
    if not is_installed:
        return {"installed": False, "running": False, "message": "Docker belum terinstall di sistem operasi ini. Harap install Docker terlebih dahulu untuk menggunakan fitur ini."}
    try:
        client = docker.from_env()
        client.ping()
        return {"installed": True, "running": True, "message": "Docker berjalan normal."}
    except Exception:
        return {"installed": True, "running": False, "message": "Docker terinstall, tetapi daemon tidak berjalan atau akses ditolak. Harap jalankan service Docker."}


def ensure_default_host(db: Session) -> DockerHost:
    """Ensure at least one 'local' DockerHost exists."""
    host = db.query(DockerHost).filter(DockerHost.connection_type == "local").first()
    if not host:
        host = DockerHost(name="Local Environment", connection_type="local")
        db.add(host)
        db.commit()
        db.refresh(host)
    return host


def get_hosts(db: Session) -> list[DockerHost]:
    """Get all active docker hosts."""
    return db.query(DockerHost).filter(DockerHost.is_active == True).all()


def _get_client(host: DockerHost) -> docker.DockerClient:
    """Instantiate a docker client based on host configuration."""
    if host.connection_type == "local":
        return docker.from_env()
    
    if not host.base_url:
        raise ValueError("Remote TCP connection requires a base_url.")
    
    return docker.DockerClient(base_url=host.base_url)


def list_containers(db: Session, host_id: int) -> dict[str, Any]:
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        containers = client.containers.list(all=True)
        return {
            "ok": True,
            "containers": [
                {
                    "id": c.id,
                    "short_id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": " ".join(c.image.tags) if getattr(c.image, 'tags', None) else c.image.id if c.image else "Unknown",
                    "created": c.attrs.get("Created", ""),
                } for c in containers
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_images(db: Session, host_id: int) -> dict[str, Any]:
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        images = client.images.list()
        return {
            "ok": True,
            "images": [
                {
                    "id": i.id,
                    "short_id": i.short_id,
                    "tags": i.tags,
                    "size": i.attrs.get("Size", 0),
                    "created": i.attrs.get("Created", "")
                } for i in images
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_volumes(db: Session, host_id: int) -> dict[str, Any]:
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        volumes = client.volumes.list()
        return {
            "ok": True,
            "volumes": [
                {
                    "name": v.name,
                    "driver": v.attrs.get("Driver", ""),
                    "mountpoint": v.attrs.get("Mountpoint", ""),
                    "created": v.attrs.get("CreatedAt", "")
                } for v in volumes
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_networks(db: Session, host_id: int) -> dict[str, Any]:
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        networks = client.networks.list()
        return {
            "ok": True,
            "networks": [
                {
                    "id": n.id,
                    "short_id": n.short_id,
                    "name": n.name,
                    "driver": n.attrs.get("Driver", ""),
                    "scope": n.attrs.get("Scope", "")
                } for n in networks
            ]
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def container_action(db: Session, host_id: int, container_id: str, action: str) -> dict[str, Any]:
    """Execute start, stop, restart, or remove on a container."""
    # Note: Security checks (like read-only mode validation) can be injected here.
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        c = client.containers.get(container_id)
        if action == "start":
            c.start()
        elif action == "stop":
            c.stop()
        elif action == "restart":
            c.restart()
        elif action == "remove":
            c.remove(force=True)
        else:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return {"ok": True, "message": f"Container {c.name} {action}ed successfully."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def remove_resource(db: Session, host_id: int, resource_type: str, resource_id: str) -> dict[str, Any]:
    """Execute remove on image, volume, or network."""
    host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
    if not host:
        return {"ok": False, "error": "Host not found"}
    try:
        client = _get_client(host)
        if resource_type == "image":
            client.images.remove(resource_id, force=True)
            msg = "Image"
        elif resource_type == "volume":
            v = client.volumes.get(resource_id)
            v.remove(force=True)
            msg = "Volume"
        elif resource_type == "network":
            n = client.networks.get(resource_id)
            n.remove()
            msg = "Network"
        else:
            return {"ok": False, "error": f"Unknown resource type: {resource_type}"}
        
        return {"ok": True, "message": f"{msg} deleted successfully."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
