"""Service for extracting data from Docker Containers and Volumes."""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import DockerHost
from app.services import docker_service

logger = logging.getLogger("quenza.docker_dump")

class DumpResult:
    def __init__(self, ok: bool, output_path: str = "", error: str = ""):
        self.ok = ok
        self.output_path = output_path
        self.error = error

def dump_container(db: Session, host_id: int, container_name: str, out_dir: str) -> DumpResult:
    """Export the filesystem of a container to a tarball."""
    logger.info(f"Dumping container '{container_name}' on host {host_id}...")
    try:
        host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
        if not host:
            return DumpResult(False, error="Docker Host tidak ditemukan.")

        client = docker_service._get_client(host)
        container = client.containers.get(container_name)
        
        # Save as .tar in staging out_dir
        safe_name = "".join(c if c.isalnum() else "_" for c in container_name).strip("_")
        out_file = Path(out_dir) / f"docker_container_{safe_name}.tar"
        
        with open(out_file, "wb") as f:
            for chunk in container.export():
                f.write(chunk)
                
        return DumpResult(True, output_path=str(out_file))
    except Exception as exc:
        logger.exception(f"Gagal mem-backup container '{container_name}': {exc}")
        return DumpResult(False, error=str(exc))

def dump_volume(db: Session, host_id: int, volume_name: str, out_dir: str) -> DumpResult:
    """Export a named volume by mounting it to a temporary container and pulling the archive."""
    logger.info(f"Dumping volume '{volume_name}' on host {host_id}...")
    temp_container = None
    try:
        host = db.query(DockerHost).filter(DockerHost.id == host_id).first()
        if not host:
            return DumpResult(False, error="Docker Host tidak ditemukan.")

        client = docker_service._get_client(host)
        
        # Verify volume exists first
        client.volumes.get(volume_name)
        
        # Run a temporary alpine container with the volume mounted as read-only
        temp_container = client.containers.run(
            "alpine",
            "sleep 3600",
            volumes={volume_name: {"bind": "/data", "mode": "ro"}},
            detach=True,
            remove=True
        )
        
        # Get the archive tarball of the /data folder
        stream, stat = temp_container.get_archive("/data")
        
        safe_name = "".join(c if c.isalnum() else "_" for c in volume_name).strip("_")
        out_file = Path(out_dir) / f"docker_volume_{safe_name}.tar"
        
        with open(out_file, "wb") as f:
            for chunk in stream:
                f.write(chunk)
                
        return DumpResult(True, output_path=str(out_file))
    except Exception as exc:
        logger.exception(f"Gagal mem-backup volume '{volume_name}': {exc}")
        return DumpResult(False, error=str(exc))
    finally:
        if temp_container:
            try:
                temp_container.stop(timeout=1)
            except Exception:
                pass
