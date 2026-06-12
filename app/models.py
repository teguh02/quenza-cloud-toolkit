"""ORM models for Quenza Cloud Toolkit.

Phase 3 introduces the core domain schema. Project and BackupSource are
fully wired for CRUD + the Integrated File Manager. Destination, Schedule,
and BackupLog are defined here so the schema is complete; their behavior
(cloud integration, scheduling engine, logging) lands in Phases 4-5.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    """Timezone-aware UTC now (avoids deprecated utcnow)."""
    return datetime.now(timezone.utc)


# --- Association tables -----------------------------------------------------

# Selective many-to-many: a project may target several destinations.
project_destinations = Table(
    "project_destinations",
    Base.metadata,
    Column(
        "project_id",
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "destination_id",
        ForeignKey("destinations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# --- Enums ------------------------------------------------------------------


class SourceType(str, enum.Enum):
    """Type of a backup source within a project."""

    DIRECTORY = "directory"
    FILE = "file"
    MYSQL = "mysql"
    POSTGRES = "postgres"
    DOCKER_CONTAINER = "docker_container"
    DOCKER_VOLUME = "docker_volume"


class ArchiveFormat(str, enum.Enum):
    """Output archive format for a project's backup."""

    ZIP = "zip"
    TAR_GZ = "tar.gz"


class DestinationType(str, enum.Enum):
    """Supported backup destinations."""

    LOCAL = "local"
    S3 = "s3"
    GDRIVE = "gdrive"
    FTP = "ftp"
    SCP = "scp"


# --- Core models ------------------------------------------------------------


class Project(Base):
    """A backup workspace grouping sources, a destination, and a schedule."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    archive_format: Mapped[ArchiveFormat] = mapped_column(
        SAEnum(ArchiveFormat, native_enum=False, length=16),
        default=ArchiveFormat.ZIP,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_malware_scan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    sources: Mapped[list[BackupSource]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="BackupSource.id",
    )

    destinations: Mapped[list[Destination]] = relationship(
        secondary=project_destinations,
        back_populates="projects",
    )

    schedule: Mapped[Optional[Schedule]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Project id={self.id} name={self.name!r}>"


class BackupSource(Base):
    """A single source to include in a project's backup.

    Depending on `source_type`:
      * DIRECTORY / FILE -> `path` holds the filesystem path.
      * MYSQL / POSTGRES -> connection fields are used; `path` is unused.
    """

    __tablename__ = "backup_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, native_enum=False, length=16), nullable=False
    )
    label: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    # Filesystem sources
    path: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Database sources
    db_host: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    db_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    db_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    db_user: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    # NOTE: stored as-is for Phase 3; secret handling hardened in Phase 4.
    db_password: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="sources")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BackupSource id={self.id} type={self.source_type} label={self.label!r}>"


# --- Models defined for later phases (schema completeness) ------------------


class Destination(Base):
    """A backup destination (Local/S3/Drive).

    Credentials/config are stored as a JSON-encoded string in `config_json`.
    """

    __tablename__ = "destinations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    dest_type: Mapped[DestinationType] = mapped_column(
        SAEnum(DestinationType, native_enum=False, length=16), nullable=False
    )
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    projects: Mapped[list[Project]] = relationship(
        secondary=project_destinations,
        back_populates="destinations",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Destination id={self.id} type={self.dest_type} name={self.name!r}>"


class Schedule(Base):
    """A per-project schedule executed by APScheduler (Phase 4)."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    # Simple recurrence model: frequency + time, translated to a cron trigger.
    frequency: Mapped[str] = mapped_column(String(16), default="daily", nullable=False)
    hour: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="schedule")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Schedule project_id={self.project_id} freq={self.frequency} enabled={self.is_enabled}>"


class BackupLog(Base):
    """Execution log for backup/restore operations."""

    __tablename__ = "backup_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(32), default="backup", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    archive_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BackupLog id={self.id} action={self.action} status={self.status}>"


class BackupJob(Base):
    """A background backup job with live progress for realtime monitoring.

    Distinct from BackupLog (which is the final, immutable record). A job
    moves through: queued -> running -> success|partial|failed|interrupted.
    `log_id` links to the BackupLog written when the job finishes.
    """

    __tablename__ = "backup_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    action: Mapped[str] = mapped_column(String(32), default="backup", nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)

    # queued | running | success | partial | failed | interrupted
    status: Mapped[str] = mapped_column(
        String(16), default="queued", nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_step: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    log_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<BackupJob id={self.id} status={self.status} progress={self.progress}>"


class DockerHost(Base):
    """A registered Docker daemon/host (local or remote)."""

    __tablename__ = "docker_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    connection_type: Mapped[str] = mapped_column(String(16), default="local", nullable=False)
    base_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tls_config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<DockerHost id={self.id} name={self.name!r} type={self.connection_type}>"


class AppMeta(Base):
    """Key/value table for lightweight application metadata."""

    __tablename__ = "app_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AppMeta key={self.key!r} value={self.value!r}>"


class AppSetting(Base):
    """Key/value store for application settings (timezone, notifications).

    Values are stored as strings (JSON-encoded for structured data).
    Sensitive values (SMTP password, Telegram token) are encrypted before
    being placed here.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AppSetting key={self.key!r}>"


class QuarantineLog(Base):
    """Log for files quarantined by the standalone Antivirus Scanner."""

    __tablename__ = "quarantine_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_path: Mapped[str] = mapped_column(Text, nullable=False)
    quarantined_path: Mapped[str] = mapped_column(Text, nullable=False)
    rule_matched: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    # status: "quarantined", "restored", "deleted"
    status: Mapped[str] = mapped_column(String(32), default="quarantined", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<QuarantineLog id={self.id} rule={self.rule_matched} status={self.status}>"
