"""APScheduler integration: in-process scheduling of project backups.

A single BackgroundScheduler runs inside the FastAPI process. On startup
it loads all enabled schedules from the database and registers a cron job
per project. Jobs call the backup orchestrator in a worker thread.

Schedule recurrence model (from the Schedule row):
    frequency: "daily" | "weekly" | "monthly"
    hour, minute: time of day
    day_of_week: 0=Mon .. 6=Sun  (weekly)
    day_of_month: 1..31          (monthly)
"""

from __future__ import annotations

import logging
from datetime import timezone as _tz

from apscheduler.events import EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.models import Schedule, AppSetting

logger = logging.getLogger("quenza.scheduler")

_scheduler: BackgroundScheduler | None = None


def _job_id(project_id: int) -> str:
    return f"project-backup-{project_id}"


def _run_scheduled_backup(project_id: int) -> None:
    """Job target: enqueue a background backup with the 'schedule' trigger.

    Delegating to job_service keeps scheduled runs tracked as jobs (with live
    progress) and consistent with manual runs. If the project already has an
    active job, the run is skipped (logged).
    """
    logger.info("Scheduled backup triggering for project %s", project_id)
    try:
        from app.services import job_service

        job_id = job_service.enqueue_backup(project_id, trigger="schedule")
        logger.info("Scheduled backup enqueued for project %s as job %s",
                    project_id, job_id)
    except Exception as exc:  # JobBusyError or others — never crash the scheduler
        logger.warning("Scheduled backup for project %s not started: %s",
                       project_id, exc)


def _run_scheduled_scan() -> None:
    """Job target: enqueue a background scan with the 'schedule' trigger."""
    logger.info("Scheduled Antivirus scan triggering")
    try:
        from app.services import job_service
        job_id = job_service.enqueue_scan(trigger="schedule")
        logger.info("Scheduled scan enqueued as job %s", job_id)
    except Exception as exc:
        logger.warning("Scheduled scan not started: %s", exc)


def _scheduler_timezone() -> str:
    """Return the configured global timezone name (fallback UTC)."""
    try:
        from app.services import settings_service

        return settings_service.get_timezone_name()
    except Exception:  # pragma: no cover
        return "UTC"


def _build_trigger(sched: Schedule) -> CronTrigger:
    """Translate a Schedule row into an APScheduler CronTrigger.

    The trigger uses the configured global timezone so the user's chosen
    hour/minute are interpreted in their local time.
    """
    hour = int(sched.hour or 0)
    minute = int(sched.minute or 0)
    freq = (sched.frequency or "daily").lower()
    tz = _scheduler_timezone()

    if freq == "weekly":
        dow = sched.day_of_week if sched.day_of_week is not None else 0
        return CronTrigger(day_of_week=int(dow), hour=hour, minute=minute, timezone=tz)
    if freq == "monthly":
        dom = sched.day_of_month if sched.day_of_month is not None else 1
        return CronTrigger(day=int(dom), hour=hour, minute=minute, timezone=tz)
    # default daily
    return CronTrigger(hour=hour, minute=minute, timezone=tz)


def start() -> None:
    """Create and start the scheduler, then load enabled schedules."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    _scheduler.start()
    logger.info("Scheduler started.")
    reload_jobs()


def shutdown() -> None:
    """Stop the scheduler (called on app shutdown)."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # pragma: no cover
            pass
        _scheduler = None
        logger.info("Scheduler stopped.")


def reload_jobs() -> int:
    """Reload all jobs from the database. Returns the number registered."""
    if _scheduler is None:
        return 0

    # Clear existing jobs.
    for job in _scheduler.get_jobs():
        job.remove()

    count = 0
    db = SessionLocal()
    try:
        schedules = db.query(Schedule).filter(Schedule.is_enabled.is_(True)).all()
        for sched in schedules:
            _register(sched)
            count += 1
    finally:
        db.close()

    logger.info("Loaded %s scheduled job(s).", count)
    sync_av_scan()
    return count


def sync_project(project_id: int) -> None:
    """Re-sync a single project's job after its schedule changes."""
    if _scheduler is None:
        return

    # Remove existing job if present.
    existing = _scheduler.get_job(_job_id(project_id))
    if existing:
        existing.remove()

    db = SessionLocal()
    try:
        sched = (
            db.query(Schedule)
            .filter(Schedule.project_id == project_id, Schedule.is_enabled.is_(True))
            .one_or_none()
        )
        if sched is not None:
            _register(sched)
    finally:
        db.close()


def _to_utc(dt):
    """Normalize a timezone-aware datetime to UTC for DB storage."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(_tz.utc)
    return dt.replace(tzinfo=_tz.utc)


def _register(sched: Schedule) -> None:
    """Add a job for an enabled schedule and persist its next run time."""
    if _scheduler is None:
        return
    try:
        trigger = _build_trigger(sched)
        job = _scheduler.add_job(
            _run_scheduled_backup,
            trigger=trigger,
            id=_job_id(sched.project_id),
            args=[sched.project_id],
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        # Persist next run time for display (always stored as UTC).
        if job.next_run_time is not None:
            db = SessionLocal()
            try:
                row = db.get(Schedule, sched.id)
                if row is not None:
                    row.next_run_at = _to_utc(job.next_run_time)
                    db.commit()
            finally:
                db.close()
    except Exception:  # pragma: no cover
        logger.exception("Failed to register schedule for project %s", sched.project_id)


def is_running() -> bool:
    """Return True if the scheduler is active."""
    return _scheduler is not None and _scheduler.running


def get_registered_job_ids() -> list[str]:
    """Return the list of currently registered job IDs (for health monitoring)."""
    if _scheduler is None:
        return []
    try:
        return [j.id for j in _scheduler.get_jobs()]
    except Exception:  # pragma: no cover
        return []


def _on_job_executed(event: JobExecutionEvent) -> None:
    """Listener: update next_run_at in the DB after a job executes.

    This keeps the 'Next Scheduled Backup' card on the dashboard accurate
    by refreshing next_run_at from the scheduler's computed next fire time.
    """
    if _scheduler is None:
        return
    job = _scheduler.get_job(event.job_id)
    if job is None:
        return
    # Only handle project-backup-* jobs (not AV scan, etc.)
    if not event.job_id.startswith("project-backup-"):
        return
    try:
        project_id = int(event.job_id.replace("project-backup-", ""))
    except (ValueError, TypeError):
        return
    db = SessionLocal()
    try:
        sched = (
            db.query(Schedule)
            .filter(Schedule.project_id == project_id)
            .one_or_none()
        )
        if sched is not None:
            sched.next_run_at = _to_utc(job.next_run_time)
            sched.last_run_at = _to_utc(event.scheduled_run_time)
            db.commit()
    except Exception:  # pragma: no cover
        db.rollback()
    finally:
        db.close()


def sync_av_scan() -> None:
    """Sync the standalone antivirus scan job based on global settings."""
    if _scheduler is None:
        return

    job_id = "standalone-av-scan"
    existing = _scheduler.get_job(job_id)
    if existing:
        existing.remove()

    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter_by(key="av_enabled").first()
        if setting and setting.value == "1":
            tz = _scheduler_timezone()
            # Default to running daily at 03:00 local time
            trigger = CronTrigger(hour=3, minute=0, timezone=tz)
            _scheduler.add_job(
                _run_scheduled_scan,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
            )
            logger.info("Standalone Antivirus scanner registered for 03:00 daily.")
    except Exception as exc:
        logger.exception("Failed to sync AV scan schedule.")
    finally:
        db.close()
