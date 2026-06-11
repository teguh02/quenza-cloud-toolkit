"""Background service that computes & caches the total size of a project's
backup sources.

Why background: walking a large directory tree (millions of files) can take
seconds and must never block the request/event loop. Results are cached in the
`app_settings` table under the key ``project_size:{id}`` (JSON) so the project
detail page can show the last known total instantly and refresh it live.

Scope decisions (see project history):
  * Only DIRECTORY and FILE sources contribute bytes to the total.
  * MYSQL / POSTGRES sources have no cheap on-disk size, so they are excluded
    from the byte total and merely counted (shown as "+N database").

Concurrency model mirrors job_service: a small bounded ThreadPoolExecutor plus
a per-project in-memory guard so the same project isn't computed twice at once.
State lives in the DB, so polling works regardless of which thread runs.
In-process; correct for a single uvicorn worker.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AppSetting, BackupSource, Project, SourceType
from app.services.archive_service import human_size

logger = logging.getLogger("quenza.sizes")

# --- Status values ----------------------------------------------------------
STATUS_IDLE = "idle"            # never computed
STATUS_COMPUTING = "computing"  # a background computation is in progress
STATUS_DONE = "done"            # cache holds a valid result
STATUS_ERROR = "error"          # last computation failed

# How long a "done" result stays fresh before an auto-recompute is allowed.
STALE_AFTER_SECONDS = 10 * 60   # 10 minutes

_KEY_PREFIX = "project_size:"

# Bounded pool for size computations (separate from the backup job pool).
_MAX_WORKERS = 2
_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()
# project_id -> True while a computation is queued/running.
_computing: set[int] = set()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS, thread_name_prefix="quenza-size"
        )
    return _executor


def _key(project_id: int) -> str:
    return f"{_KEY_PREFIX}{project_id}"


def _default_entry() -> dict:
    return {
        "status": STATUS_IDLE,
        "total_bytes": 0,
        "total_human": human_size(0),
        "dir_count": 0,
        "file_count": 0,
        "db_count": 0,
        "skipped": 0,
        "error": "",
        "computed_at": None,
    }


# --- Cache read/write (own session; safe from any thread) -------------------


def _read_raw(db: Session, project_id: int) -> str | None:
    row = db.scalars(
        select(AppSetting).where(AppSetting.key == _key(project_id))
    ).one_or_none()
    return row.value if row is not None else None


def _write_raw(db: Session, project_id: int, value: str) -> None:
    row = db.scalars(
        select(AppSetting).where(AppSetting.key == _key(project_id))
    ).one_or_none()
    if row is None:
        db.add(AppSetting(key=_key(project_id), value=value))
    else:
        row.value = value


def get_cached(db: Session, project_id: int) -> dict:
    """Return the cached size entry for a project (default 'idle' if none)."""
    raw = _read_raw(db, project_id)
    if not raw:
        return _default_entry()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _default_entry()
    entry = _default_entry()
    entry.update({k: v for k, v in data.items() if k in entry})
    return entry


def _store(project_id: int, entry: dict) -> None:
    db = SessionLocal()
    try:
        _write_raw(db, project_id, json.dumps(entry, ensure_ascii=False))
        db.commit()
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("Failed to store size cache for project %s", project_id)
    finally:
        db.close()


# --- Staleness --------------------------------------------------------------


def is_stale(entry: dict) -> bool:
    """Return True if the cached entry should be (re)computed automatically."""
    status = entry.get("status")
    if status in (STATUS_IDLE, STATUS_ERROR):
        return True
    if status == STATUS_COMPUTING:
        return False  # already running
    computed_at = entry.get("computed_at")
    if not computed_at:
        return True
    try:
        ts = datetime.fromisoformat(computed_at)
    except (ValueError, TypeError):
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (_utcnow() - ts).total_seconds()
    return age >= STALE_AFTER_SECONDS


# --- Size computation -------------------------------------------------------


def _dir_size(path: str) -> tuple[int, int, int]:
    """Return (total_bytes, files_counted, files_skipped) for a directory.

    Symlinks are not followed (avoids cycles / double counting). Unreadable
    entries are skipped gracefully.
    """
    total = 0
    counted = 0
    skipped = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        # Skip directories we can't traverse (best-effort).
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                st = os.stat(fpath, follow_symlinks=False)
                total += st.st_size
                counted += 1
            except (OSError, PermissionError, ValueError):
                skipped += 1
    return total, counted, skipped


def _compute(project_id: int) -> None:
    """Worker body: load sources, sum sizes, write result to the cache."""
    db = SessionLocal()
    try:
        project = db.get(Project, project_id)
        if project is None:
            return
        sources = list(project.sources)
    finally:
        db.close()

    total = 0
    dir_count = 0
    file_count = 0
    db_count = 0
    skipped = 0

    for s in sources:
        try:
            if s.source_type == SourceType.DIRECTORY:
                if s.path and os.path.isdir(s.path):
                    bytes_, _counted, skip = _dir_size(s.path)
                    total += bytes_
                    skipped += skip
                else:
                    skipped += 1
                dir_count += 1
            elif s.source_type == SourceType.FILE:
                if s.path and os.path.isfile(s.path):
                    try:
                        total += os.stat(s.path, follow_symlinks=False).st_size
                    except (OSError, PermissionError, ValueError):
                        skipped += 1
                else:
                    skipped += 1
                file_count += 1
            else:
                # MYSQL / POSTGRES: excluded from the byte total, only counted.
                db_count += 1
        except Exception:  # pragma: no cover - never let one source crash all
            logger.exception("Size computation failed for source %s", getattr(s, "id", "?"))
            skipped += 1

    entry = {
        "status": STATUS_DONE,
        "total_bytes": total,
        "total_human": human_size(total),
        "dir_count": dir_count,
        "file_count": file_count,
        "db_count": db_count,
        "skipped": skipped,
        "error": "",
        "computed_at": _utcnow().isoformat(),
    }
    _store(project_id, entry)
    logger.info(
        "Computed size for project %s: %s (%s dir, %s file, %s db, %s skipped)",
        project_id, entry["total_human"], dir_count, file_count, db_count, skipped,
    )


def _run(project_id: int) -> None:
    try:
        _compute(project_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Size worker crashed for project %s", project_id)
        entry = get_cached(SessionLocal(), project_id)  # best effort
        entry.update({"status": STATUS_ERROR, "error": str(exc)})
        _store(project_id, entry)
    finally:
        with _lock:
            _computing.discard(project_id)


def enqueue_compute(project_id: int, *, force: bool = False) -> bool:
    """Schedule a background size computation for a project.

    Returns True if a computation was scheduled, False if one was already
    running (or, when force is False, not needed).

    The caller is expected to have decided staleness; pass force=True for an
    explicit "recompute" action.
    """
    with _lock:
        if project_id in _computing:
            return False
        _computing.add(project_id)

    # Mark the cache as computing so the UI reflects it immediately.
    entry = get_cached(SessionLocal(), project_id)
    entry["status"] = STATUS_COMPUTING
    if force:
        entry["error"] = ""
    _store(project_id, entry)

    try:
        _get_executor().submit(_run, project_id)
    except Exception:
        with _lock:
            _computing.discard(project_id)
        entry["status"] = STATUS_ERROR
        entry["error"] = "Gagal menjadwalkan perhitungan."
        _store(project_id, entry)
        raise
    logger.info("Enqueued size computation for project %s (force=%s)", project_id, force)
    return True


def ensure_fresh(db: Session, project_id: int) -> dict:
    """Return the cached entry, kicking off a background recompute if stale.

    Used by the project detail page: it returns instantly with whatever is
    cached (possibly 'idle'/'computing'); the client then polls until 'done'.
    """
    entry = get_cached(db, project_id)
    if is_stale(entry):
        try:
            enqueue_compute(project_id, force=False)
            entry["status"] = STATUS_COMPUTING
        except Exception:  # pragma: no cover
            logger.exception("Failed to auto-enqueue size for project %s", project_id)
    return entry


def shutdown() -> None:
    """Shut down the executor (called on app shutdown)."""
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
