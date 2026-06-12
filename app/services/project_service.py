"""Project service: CRUD for projects and their backup sources.

All database access for the Projects feature lives here so routes stay
thin. Functions raise ValueError for validation problems and return ORM
objects on success.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    ArchiveFormat,
    BackupSource,
    Project,
    SourceType,
)

# --- Projects ---------------------------------------------------------------


def list_projects(db: Session) -> list[Project]:
    """Return all projects, newest first."""
    stmt = select(Project).order_by(Project.created_at.desc())
    return list(db.scalars(stmt).all())


def get_project(db: Session, project_id: int) -> Project | None:
    """Return a project by id, or None if not found."""
    return db.get(Project, project_id)


def create_project(
    db: Session,
    *,
    name: str,
    description: str = "",
    archive_format: str = "zip",
) -> Project:
    """Create a new project.

    Raises:
        ValueError: if the name is empty or the archive format is invalid.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Nama project tidak boleh kosong.")
    if len(name) > 120:
        raise ValueError("Nama project maksimal 120 karakter.")

    fmt = _parse_archive_format(archive_format)

    project = Project(
        name=name,
        description=(description or "").strip(),
        archive_format=fmt,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(
    db: Session,
    project_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    archive_format: str | None = None,
    is_active: bool | None = None,
    enable_malware_scan: bool | None = None,
) -> Project:
    """Update an existing project.

    Raises:
        ValueError: if the project does not exist or a field is invalid.
    """
    project = get_project(db, project_id)
    if project is None:
        raise ValueError("Project tidak ditemukan.")

    if name is not None:
        clean = name.strip()
        if not clean:
            raise ValueError("Nama project tidak boleh kosong.")
        if len(clean) > 120:
            raise ValueError("Nama project maksimal 120 karakter.")
        project.name = clean

    if description is not None:
        project.description = description.strip()

    if archive_format is not None:
        project.archive_format = _parse_archive_format(archive_format)

    if is_active is not None:
        project.is_active = bool(is_active)

    if enable_malware_scan is not None:
        project.enable_malware_scan = bool(enable_malware_scan)

    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project_id: int) -> bool:
    """Delete a project (and its sources via cascade).

    Returns:
        True if deleted, False if it did not exist.
    """
    project = get_project(db, project_id)
    if project is None:
        return False
    db.delete(project)
    db.commit()
    return True


def count_sources(db: Session, project_id: int) -> int:
    """Return the number of sources attached to a project."""
    stmt = select(func.count(BackupSource.id)).where(
        BackupSource.project_id == project_id
    )
    return int(db.scalar(stmt) or 0)


# --- Backup sources ---------------------------------------------------------


def add_source(
    db: Session,
    project_id: int,
    *,
    source_type: str,
    label: str = "",
    path: str = "",
    db_host: str = "",
    db_port: int | None = None,
    db_name: str = "",
    db_user: str = "",
    db_password: str = "",
) -> BackupSource:
    """Add a backup source to a project.

    Validates required fields per source type.

    Raises:
        ValueError: if the project is missing or required fields are absent.
    """
    project = get_project(db, project_id)
    if project is None:
        raise ValueError("Project tidak ditemukan.")

    stype = _parse_source_type(source_type)

    if stype in (SourceType.DIRECTORY, SourceType.FILE):
        if not (path or "").strip():
            raise ValueError("Path tidak boleh kosong untuk sumber direktori/file.")
            
        clean_path = path.strip()
        
        # Validation for duplicate source
        existing = db.scalars(
            select(BackupSource)
            .where(BackupSource.project_id == project_id)
            .where(BackupSource.source_type == stype)
            .where(BackupSource.path == clean_path)
        ).first()
        
        if existing:
            raise ValueError("Sumber direktori sudah ada.")
            
        source = BackupSource(
            project_id=project_id,
            source_type=stype,
            label=(label or "").strip(),
            path=clean_path,
        )
    else:  # MYSQL / POSTGRES
        if not (db_name or "").strip():
            raise ValueError("Nama/Identifier wajib diisi.")
        if not (db_host or "").strip():
            raise ValueError("Host wajib diisi.")
        source = BackupSource(
            project_id=project_id,
            source_type=stype,
            label=(label or "").strip() or db_name.strip(),
            db_host=db_host.strip(),
            db_port=db_port,
            db_name=db_name.strip(),
            db_user=(db_user or "").strip(),
            db_password=db_password or "",
        )

    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def get_source(db: Session, source_id: int) -> BackupSource | None:
    """Return a source by id, or None."""
    return db.get(BackupSource, source_id)


def delete_source(db: Session, project_id: int, source_id: int) -> bool:
    """Delete a source belonging to the given project.

    Returns:
        True if deleted, False if not found / mismatched project.
    """
    source = get_source(db, source_id)
    if source is None or source.project_id != project_id:
        return False
    db.delete(source)
    db.commit()
    return True


# --- Helpers ----------------------------------------------------------------


def _parse_archive_format(value: str) -> ArchiveFormat:
    """Coerce a string into ArchiveFormat or raise ValueError."""
    try:
        return ArchiveFormat(value)
    except ValueError:
        raise ValueError(
            "Format arsip tidak valid. Gunakan 'zip' atau 'tar.gz'."
        ) from None


def _parse_source_type(value: str) -> SourceType:
    """Coerce a string into SourceType or raise ValueError."""
    try:
        return SourceType(value)
    except ValueError:
        raise ValueError(
            "Tipe sumber tidak valid (directory/file/mysql/postgres/docker_container/docker_volume)."
        ) from None


def source_type_meta(source: BackupSource) -> dict[str, str]:
    """Return display metadata (icon/tone/fg/summary) for a source."""
    mapping = {
        SourceType.DIRECTORY: ("folder", "pastel-blue", "text-blue-500"),
        SourceType.FILE: ("list", "pastel-green", "text-brand-teal"),
        SourceType.MYSQL: ("cloud", "pastel-orange", "text-amber-500"),
        SourceType.POSTGRES: ("cloud", "pastel-purple", "text-purple-500"),
        SourceType.DOCKER_CONTAINER: ("box", "pastel-blue", "text-blue-600"),
        SourceType.DOCKER_VOLUME: ("hard-drive", "pastel-green", "text-green-600"),
    }
    icon, tone, fg = mapping[source.source_type]

    if source.source_type in (SourceType.DIRECTORY, SourceType.FILE):
        summary = source.path
    elif source.source_type in (SourceType.DOCKER_CONTAINER, SourceType.DOCKER_VOLUME):
        # We store DockerHost ID in db_host, and the actual container/volume name in db_name
        summary = f"Host #{source.db_host} : {source.db_name}"
    else:
        port = f":{source.db_port}" if source.db_port else ""
        summary = f"{source.db_user}@{source.db_host}{port}/{source.db_name}"

    return {
        "icon": icon,
        "tone": tone,
        "fg": fg,
        "summary": summary,
        "type_label": source.source_type.value,
    }
