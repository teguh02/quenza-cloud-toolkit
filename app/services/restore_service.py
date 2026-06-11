"""Restore service: download a backup archive and extract it safely.

Restore is intentionally passive and safe:
  * Only downloads the selected archive from a destination and extracts it
    into a user-specified target directory.
  * No automatic actions (no database import, no command execution).
  * Extraction is guarded against path traversal (zip-slip / tar-slip):
    any member that would escape the target directory is rejected and the
    whole restore fails.

Every restore is recorded as a BackupLog row with action="restore".
"""

from __future__ import annotations

import json
import logging
import os
import tarfile
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BackupLog, Destination
from app.services.destinations import get_adapter

logger = logging.getLogger("quenza.restore")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_archives(db: Session, destination_id: int) -> tuple[bool, list[dict], str]:
    """List archives available at a destination.

    Returns:
        (ok, entries, error_message)
    """
    dest = db.get(Destination, destination_id)
    if dest is None:
        return False, [], "Destinasi tidak ditemukan."

    try:
        config = json.loads(dest.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    adapter = get_adapter(dest.dest_type.value, config)
    if adapter is None:
        return False, [], "Adapter destinasi tidak dikenal."

    result = adapter.list_archives()
    if not result.ok:
        return False, [], result.error or "Gagal mendaftar arsip."

    entries = [
        {
            "name": e.name,
            "size": e.size,
            "modified": e.modified,
            "ref": e.ref,
        }
        for e in result.entries
    ]
    return True, entries, ""


def _is_within(base: Path, target: Path) -> bool:
    """Return True if `target` is inside `base` (after resolving)."""
    try:
        base_r = base.resolve()
        target_r = target.resolve()
        return base_r == target_r or base_r in target_r.parents
    except (OSError, RuntimeError):
        return False


def _safe_extract_zip(zip_path: str, dest_dir: Path) -> tuple[int, str | None]:
    """Extract a ZIP archive safely. Returns (files_extracted, error)."""
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            # Reject absolute paths and traversal.
            target = dest_dir / member
            if not _is_within(dest_dir, target):
                return 0, f"Entri arsip tidak aman ditolak: {member}"
        zf.extractall(dest_dir)
        count = len([n for n in zf.namelist() if not n.endswith("/")])
    return count, None


def _safe_extract_tar(tar_path: str, dest_dir: Path) -> tuple[int, str | None]:
    """Extract a tar.gz archive safely. Returns (files_extracted, error)."""
    count = 0
    with tarfile.open(tar_path, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            target = dest_dir / member.name
            if not _is_within(dest_dir, target):
                return 0, f"Entri arsip tidak aman ditolak: {member.name}"
            # Reject special files (devices, etc.) - only allow files/dirs/links.
            if not (member.isreg() or member.isdir() or member.issym() or member.islnk()):
                return 0, f"Tipe entri tidak diizinkan: {member.name}"
        tf.extractall(dest_dir)
        count = len([m for m in members if m.isreg()])
    return count, None


def _extract(archive_path: str, dest_dir: Path) -> tuple[int, str | None]:
    """Dispatch extraction based on file extension."""
    lower = archive_path.lower()
    try:
        if lower.endswith(".zip"):
            return _safe_extract_zip(archive_path, dest_dir)
        if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
            return _safe_extract_tar(archive_path, dest_dir)
        return 0, "Format arsip tidak didukung untuk restore."
    except zipfile.BadZipFile:
        return 0, "Arsip ZIP rusak atau tidak valid."
    except tarfile.TarError as exc:
        return 0, f"Arsip tar.gz tidak valid: {exc}"
    except (OSError, PermissionError) as exc:
        return 0, f"Gagal mengekstrak: {exc}"


def run_restore(
    destination_id: int,
    archive_ref: str,
    archive_name: str,
    target_dir: str,
) -> dict:
    """Download `archive_ref` from a destination and extract into target_dir.

    Returns a summary dict and writes a BackupLog (action="restore").
    """
    started = time.monotonic()
    db: Session = SessionLocal()
    staging: str | None = None

    try:
        target = (target_dir or "").strip()
        if not target:
            return _finalize(db, None, "Direktori tujuan belum diisi.", "failed", started)

        dest = db.get(Destination, destination_id)
        if dest is None:
            return _finalize(db, None, "Destinasi tidak ditemukan.", "failed", started)

        dest_name = dest.name

        # Validate/create the target directory.
        try:
            target_path = Path(target)
            target_path.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as exc:
            return _finalize(
                db, dest_name, f"Direktori tujuan tidak dapat dibuat: {exc}",
                "failed", started,
            )

        # Build adapter.
        try:
            config = json.loads(dest.config_json or "{}")
        except json.JSONDecodeError:
            config = {}
        adapter = get_adapter(dest.dest_type.value, config)
        if adapter is None:
            return _finalize(db, dest_name, "Adapter destinasi tidak dikenal.", "failed", started)

        # 1) Download into staging.
        staging = tempfile.mkdtemp(prefix="quenza_restore_")
        dl = adapter.download(archive_ref, staging)
        if not dl.ok:
            return _finalize(db, dest_name, f"Unduh gagal: {dl.error}", "failed", started)

        # 2) Extract safely into the target directory.
        files, err = _extract(dl.local_path, target_path)
        if err:
            return _finalize(
                db, dest_name, err, "failed", started,
                detail={"archive": archive_name, "target": target},
            )

        message = f"Restore berhasil: {files} file diekstrak ke {target}."
        return _finalize(
            db, dest_name, message, "success", started,
            detail={
                "archive": archive_name,
                "target": target,
                "files_extracted": files,
            },
            archive_name=archive_name,
        )

    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Unexpected restore error")
        return _finalize(db, None, f"Kesalahan tak terduga: {exc}", "failed", started)
    finally:
        if staging:
            import shutil

            shutil.rmtree(staging, ignore_errors=True)
        db.close()


def _finalize(
    db: Session,
    dest_name: str | None,
    message: str,
    status: str,
    started_monotonic: float,
    *,
    detail: dict | None = None,
    archive_name: str = "",
) -> dict:
    """Persist a restore BackupLog and return a summary dict."""
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    detail = detail or {}
    if dest_name:
        detail.setdefault("destination", dest_name)

    log = BackupLog(
        project_id=None,
        project_name=dest_name or "",
        action="restore",
        status=status,
        trigger="manual",
        message=message,
        detail_json=json.dumps(detail, ensure_ascii=False),
        archive_name=archive_name,
        size_bytes=0,
        duration_ms=duration_ms,
    )
    try:
        db.add(log)
        db.commit()
        db.refresh(log)
        log_id = log.id
    except Exception:  # pragma: no cover
        db.rollback()
        log_id = None

    result = {
        "ok": status == "success",
        "status": status,
        "message": message,
        "log_id": log_id,
        "duration_ms": duration_ms,
        "detail": detail,
    }

    # Best-effort notification (never affects restore outcome).
    try:
        from app.services import notification_service

        notification_service.notify_restore_result(result, source_name=dest_name or "")
    except Exception:  # pragma: no cover
        logger.exception("Restore notification dispatch failed")

    return result
