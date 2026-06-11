"""Backup orchestrator: dump -> archive -> upload -> log.

`run_backup` executes a project's full backup pipeline and writes a
BackupLog row. It is safe to call from a request handler or from the
scheduler thread. It opens its own DB session so it does not depend on a
request-scoped session.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import (
    ArchiveFormat,
    BackupLog,
    Project,
    Schedule,
    SourceType,
)
from app.services import archive_service, db_dump_service
from app.services.destinations import get_adapter

logger = logging.getLogger("quenza.backup")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_slug() -> str:
    return _utcnow().strftime("%Y%m%d_%H%M%S")


def _safe_name(name: str) -> str:
    keep = "-_."
    cleaned = "".join(c if (c.isalnum() or c in keep) else "_" for c in name)
    return cleaned.strip("_") or "project"


def run_backup(project_id: int, *, trigger: str = "manual") -> dict:
    """Run a backup for the given project id.

    Args:
        project_id: target project.
        trigger: "manual" or "schedule".

    Returns:
        A summary dict (also persisted as a BackupLog).
    """
    started = time.monotonic()
    db: Session = SessionLocal()
    staging: str | None = None

    try:
        project = db.get(Project, project_id)
        if project is None:
            return _finalize(
                db, None, "Project tidak ditemukan.", "failed", trigger, started, {}
            )

        project_name = project.name
        sources = list(project.sources)
        destinations = list(project.destinations)
        archive_format = (
            project.archive_format.value
            if isinstance(project.archive_format, ArchiveFormat)
            else str(project.archive_format)
        )

        if not sources:
            return _finalize(
                db, project, "Tidak ada sumber backup pada project ini.",
                "failed", trigger, started, {},
            )
        if not destinations:
            return _finalize(
                db, project, "Tidak ada destinasi terpilih pada project ini.",
                "failed", trigger, started, {},
            )

        # 1) Staging directory
        staging = tempfile.mkdtemp(prefix=f"quenza_bkp_{project_id}_")
        dump_dir = Path(staging) / "_dumps"
        dump_dir.mkdir(parents=True, exist_ok=True)

        # 2) Collect archive items (filesystem sources + DB dumps)
        items: list[archive_service.ArchiveItem] = []
        source_warnings: list[str] = []

        for src in sources:
            if src.source_type in (SourceType.DIRECTORY, SourceType.FILE):
                if src.path:
                    items.append(archive_service.ArchiveItem(path=src.path))
                else:
                    source_warnings.append("Sumber path kosong dilewati.")
            elif src.source_type == SourceType.MYSQL:
                res = db_dump_service.dump_mysql(
                    host=src.db_host, port=src.db_port, name=src.db_name,
                    user=src.db_user, password=src.db_password, out_dir=str(dump_dir),
                )
                if res.ok:
                    items.append(archive_service.ArchiveItem(path=res.output_path))
                else:
                    source_warnings.append(f"MySQL {src.db_name}: {res.error}")
            elif src.source_type == SourceType.POSTGRES:
                res = db_dump_service.dump_postgres(
                    host=src.db_host, port=src.db_port, name=src.db_name,
                    user=src.db_user, password=src.db_password, out_dir=str(dump_dir),
                )
                if res.ok:
                    items.append(archive_service.ArchiveItem(path=res.output_path))
                else:
                    source_warnings.append(f"PostgreSQL {src.db_name}: {res.error}")

        if not items:
            detail = {"warnings": source_warnings}
            return _finalize(
                db, project,
                "Semua sumber gagal disiapkan (tidak ada yang bisa diarsipkan).",
                "failed", trigger, started, detail,
            )

        # 3) Create archive
        ext = "zip" if archive_format == "zip" else "tar.gz"
        archive_name = f"{_safe_name(project_name)}_{_timestamp_slug()}.{ext}"
        archive_path = str(Path(staging) / archive_name)

        arch = archive_service.create_archive(
            items, archive_path, archive_format=archive_format
        )
        if not arch.ok:
            detail = {"warnings": source_warnings, "skipped": arch.skipped}
            return _finalize(
                db, project, f"Pengarsipan gagal: {arch.error}",
                "failed", trigger, started, detail,
            )

        # 4) Upload to each destination
        upload_results: list[dict] = []
        any_ok = False
        for dest in destinations:
            try:
                config = json.loads(dest.config_json or "{}")
            except json.JSONDecodeError:
                config = {}
            adapter = get_adapter(dest.dest_type.value, config)
            if adapter is None:
                upload_results.append(
                    {"destination": dest.name, "ok": False, "error": "Adapter tidak dikenal."}
                )
                continue
            up = adapter.upload(archive_path, archive_name)
            upload_results.append(
                {
                    "destination": dest.name,
                    "type": dest.dest_type.value,
                    "ok": up.ok,
                    "location": up.location,
                    "error": up.error,
                }
            )
            any_ok = any_ok or up.ok

        # 5) Determine status
        all_ok = all(r["ok"] for r in upload_results)
        if all_ok and not source_warnings:
            status = "success"
            message = f"Backup berhasil ke {len(upload_results)} destinasi."
        elif any_ok:
            status = "partial"
            message = "Backup selesai sebagian (ada destinasi/sumber yang gagal)."
        else:
            status = "failed"
            message = "Backup gagal di semua destinasi."

        detail = {
            "warnings": source_warnings,
            "skipped": arch.skipped,
            "uploads": upload_results,
            "files_added": arch.files_added,
        }
        return _finalize(
            db, project, message, status, trigger, started, detail,
            archive_name=archive_name, size_bytes=arch.size_bytes,
        )

    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Unexpected backup error for project %s", project_id)
        return _finalize(
            db, None, f"Kesalahan tak terduga: {exc}", "failed", trigger, started, {}
        )
    finally:
        # Always clean up staging.
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        db.close()


def _finalize(
    db: Session,
    project: Project | None,
    message: str,
    status: str,
    trigger: str,
    started_monotonic: float,
    detail: dict,
    *,
    archive_name: str = "",
    size_bytes: int = 0,
) -> dict:
    """Persist a BackupLog and return a summary dict."""
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)

    log = BackupLog(
        project_id=project.id if project else None,
        project_name=project.name if project else "",
        action="backup",
        status=status,
        trigger=trigger,
        message=message,
        detail_json=json.dumps(detail, ensure_ascii=False),
        archive_name=archive_name,
        size_bytes=size_bytes,
        duration_ms=duration_ms,
    )
    try:
        db.add(log)
        # Update schedule last_run if applicable.
        if project is not None and trigger == "schedule":
            sched = project.schedule
            if isinstance(sched, Schedule):
                sched.last_run_at = _utcnow()
        db.commit()
        db.refresh(log)
        log_id = log.id
    except Exception:  # pragma: no cover
        db.rollback()
        log_id = None

    return {
        "ok": status in ("success", "partial"),
        "status": status,
        "message": message,
        "log_id": log_id,
        "archive_name": archive_name,
        "size_bytes": size_bytes,
        "duration_ms": duration_ms,
        "detail": detail,
    }
