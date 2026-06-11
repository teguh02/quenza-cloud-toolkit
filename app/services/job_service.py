"""Background job service for backups (in-process executor + DB-backed state).

Runs backups off the request/event loop so the web UI stays responsive and
reverse proxies don't time out. Progress is written to the `backup_jobs`
table and polled by the History page.

Concurrency model:
  * A bounded ThreadPoolExecutor (default 2 workers) runs jobs.
  * A per-project in-memory lock + a DB check prevents the same project from
    running twice concurrently.
  * State lives in the DB so polling works regardless of which thread runs.

Note: this is in-process. With a single uvicorn worker (the default for the
installed service) this is correct. With multiple workers, add DB-level job
claiming (documented in README → Future Work).
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import BackupJob

logger = logging.getLogger("quenza.jobs")

# Bounded pool: how many backups may run in parallel.
_MAX_WORKERS = 2
_executor: ThreadPoolExecutor | None = None

# Guards _running_projects and lazy executor creation.
_lock = threading.Lock()
# project_id -> True while a job for that project is queued/running.
_running_projects: set[int] = set()

_ACTIVE_STATUSES = ("queued", "running")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS, thread_name_prefix="quenza-job"
        )
    return _executor


class JobBusyError(RuntimeError):
    """Raised when a project already has an active job."""


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------
def enqueue_backup(project_id: int, trigger: str = "manual") -> int:
    """Create a queued BackupJob and submit it to the executor.

    Returns the job id immediately (non-blocking).

    Raises:
        JobBusyError: if this project already has an active job.
    """
    with _lock:
        if project_id in _running_projects:
            raise JobBusyError("Backup untuk project ini sedang berjalan.")
        # Double-check the DB in case of restart / other path.
        if _project_has_active_job(project_id):
            raise JobBusyError("Backup untuk project ini sedang berjalan.")
        _running_projects.add(project_id)

    # Create the job row.
    db = SessionLocal()
    try:
        project_name = ""
        from app.models import Project

        proj = db.get(Project, project_id)
        if proj is not None:
            project_name = proj.name
        job = BackupJob(
            project_id=project_id,
            project_name=project_name,
            action="backup",
            trigger=trigger,
            status="queued",
            progress=0,
            current_step="Menunggu antrian...",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    except Exception:
        # Roll back the in-memory lock on failure.
        with _lock:
            _running_projects.discard(project_id)
        db.rollback()
        raise
    finally:
        db.close()

    try:
        _get_executor().submit(_run_job, job_id, project_id, trigger)
    except Exception:  # pragma: no cover - executor submission failure
        with _lock:
            _running_projects.discard(project_id)
        _update_job(job_id, status="failed", message="Gagal menjadwalkan job.",
                    finished_at=_utcnow())
        raise

    logger.info("Enqueued backup job %s for project %s (%s)", job_id, project_id, trigger)
    return job_id


def _project_has_active_job(project_id: int) -> bool:
    db = SessionLocal()
    try:
        stmt = select(BackupJob.id).where(
            BackupJob.project_id == project_id,
            BackupJob.status.in_(_ACTIVE_STATUSES),
        ).limit(1)
        return db.scalars(stmt).first() is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _run_job(job_id: int, project_id: int, trigger: str) -> None:
    """Execute the backup, updating job progress along the way."""
    _update_job(job_id, status="running", started_at=_utcnow(),
                current_step="Memulai...", progress=1)

    def progress_cb(step_index: int, label: str, pct: int, total_steps: int) -> None:
        _update_job(
            job_id,
            progress=max(0, min(100, int(pct))),
            current_step=label,
            step_index=step_index,
            total_steps=total_steps,
        )

    try:
        from app.services import backup_service

        result = backup_service.run_backup(
            project_id, trigger=trigger, progress_cb=progress_cb
        )
        status = result.get("status", "failed")
        _update_job(
            job_id,
            status=status if status in ("success", "partial", "failed") else "failed",
            progress=100,
            current_step="Selesai." if status != "failed" else "Gagal.",
            message=result.get("message", ""),
            detail_json=json.dumps(result.get("detail", {}), ensure_ascii=False),
            log_id=result.get("log_id"),
            finished_at=_utcnow(),
        )
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Backup job %s crashed", job_id)
        _update_job(job_id, status="failed", progress=100,
                    current_step="Gagal.", message=f"Kesalahan tak terduga: {exc}",
                    finished_at=_utcnow())
    finally:
        with _lock:
            _running_projects.discard(project_id)


def _update_job(job_id: int, **fields) -> None:
    """Apply field updates to a BackupJob row (best-effort)."""
    db = SessionLocal()
    try:
        job = db.get(BackupJob, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        db.commit()
    except Exception:  # pragma: no cover
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Queries (for the API / History page)
# ---------------------------------------------------------------------------
def _job_to_dict(job: BackupJob) -> dict:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "project_name": job.project_name,
        "action": job.action,
        "trigger": job.trigger,
        "status": job.status,
        "progress": job.progress,
        "current_step": job.current_step,
        "step_index": job.step_index,
        "total_steps": job.total_steps,
        "message": job.message,
        "log_id": job.log_id,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


def list_active(db: Session) -> list[dict]:
    """Return queued/running jobs (newest first)."""
    stmt = (
        select(BackupJob)
        .where(BackupJob.status.in_(_ACTIVE_STATUSES))
        .order_by(BackupJob.created_at.desc())
    )
    return [_job_to_dict(j) for j in db.scalars(stmt).all()]


def get(db: Session, job_id: int) -> dict | None:
    job = db.get(BackupJob, job_id)
    return _job_to_dict(job) if job is not None else None


def active_count(db: Session) -> int:
    from sqlalchemy import func

    stmt = select(func.count(BackupJob.id)).where(
        BackupJob.status.in_(_ACTIVE_STATUSES)
    )
    return int(db.scalar(stmt) or 0)


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------
def mark_interrupted_on_startup() -> int:
    """Mark any leftover active jobs as interrupted (called on app startup).

    In-process executor state is lost on restart, so queued/running rows from
    a previous process must not appear 'stuck'. Returns the count updated.
    """
    db = SessionLocal()
    try:
        stmt = select(BackupJob).where(BackupJob.status.in_(_ACTIVE_STATUSES))
        jobs = list(db.scalars(stmt).all())
        for job in jobs:
            job.status = "interrupted"
            job.message = job.message or "Terputus karena layanan dimulai ulang."
            job.finished_at = _utcnow()
        if jobs:
            db.commit()
        return len(jobs)
    except Exception:  # pragma: no cover
        db.rollback()
        return 0
    finally:
        db.close()


def shutdown() -> None:
    """Shut down the executor (called on app shutdown)."""
    global _executor
    if _executor is not None:
        try:
            _executor.shutdown(wait=False, cancel_futures=True)
        except TypeError:  # pragma: no cover - older Python without cancel_futures
            _executor.shutdown(wait=False)
        except Exception:  # pragma: no cover
            pass
        _executor = None
