"""Scheduler health monitoring service.

Proactively checks the APScheduler state and detects issues such as:
  * Scheduler not running
  * Registered jobs mismatch with enabled DB schedules
  * Jobs that appear to have been missed (next_run_at in the past)

Returns a SchedulerHealth dataclass consumed by the dashboard and settings
templates to show alert banners when problems are detected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Schedule

logger = logging.getLogger("quenza.scheduler_health")

# A job whose next_run_at is more than this many minutes in the past
# (without having been updated) is considered "missed".
MISSED_THRESHOLD_MINUTES = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SchedulerHealth:
    """Result of a scheduler health check."""

    is_healthy: bool = True
    scheduler_running: bool = True
    registered_jobs: int = 0
    expected_jobs: int = 0
    missed_jobs: list[str] = field(default_factory=list)
    alerts: list[str] = field(default_factory=list)


def get_health_status(db: Session | None = None) -> SchedulerHealth:
    """Run all health checks and return a SchedulerHealth report.

    If *db* is not provided, a short-lived session is created internally.
    """
    from app import scheduler as sched_module

    health = SchedulerHealth()

    # --- Check 1: Is the scheduler running? ---------------------------------
    health.scheduler_running = sched_module.is_running()
    if not health.scheduler_running:
        health.is_healthy = False
        health.alerts.append(
            "Scheduler internal (APScheduler) tidak aktif. "
            "Backup terjadwal dan pemindaian Antivirus tidak akan berjalan."
        )
        # If scheduler is down, skip the rest — everything will be bad.
        return health

    # --- Check 2: Registered jobs vs DB enabled schedules -------------------
    registered_ids = sched_module.get_registered_job_ids()
    health.registered_jobs = len(registered_ids)

    own_db = db is None
    if own_db:
        db = SessionLocal()
    try:
        enabled_schedules = list(
            db.scalars(
                select(Schedule).where(Schedule.is_enabled.is_(True))
            ).all()
        )
        health.expected_jobs = len(enabled_schedules)

        # Build set of expected APScheduler job IDs from DB schedules.
        expected_backup_ids = {
            f"project-backup-{s.project_id}" for s in enabled_schedules
        }
        registered_set = set(registered_ids)

        missing_in_scheduler = expected_backup_ids - registered_set
        if missing_in_scheduler:
            health.is_healthy = False
            count = len(missing_in_scheduler)
            health.alerts.append(
                f"{count} jadwal backup aktif di database tidak terdaftar di scheduler. "
                "Coba restart aplikasi atau simpan ulang jadwal yang bermasalah."
            )

        # --- Check 3: Missed jobs (next_run_at is past the threshold) -------
        cutoff = _utcnow() - timedelta(minutes=MISSED_THRESHOLD_MINUTES)
        for sched in enabled_schedules:
            if sched.next_run_at is None:
                continue
            nra = sched.next_run_at
            if nra.tzinfo is None:
                nra = nra.replace(tzinfo=timezone.utc)
            if nra < cutoff:
                project_name = ""
                if sched.project:
                    project_name = sched.project.name
                health.missed_jobs.append(
                    project_name or f"Project #{sched.project_id}"
                )

        if health.missed_jobs:
            health.is_healthy = False
            names = ", ".join(health.missed_jobs[:5])
            suffix = (
                f" dan {len(health.missed_jobs) - 5} lainnya"
                if len(health.missed_jobs) > 5
                else ""
            )
            health.alerts.append(
                f"Jadwal backup tampak terlewat untuk: {names}{suffix}. "
                "Waktu backup berikutnya sudah lewat tanpa pembaruan. "
                "Pastikan aplikasi berjalan terus-menerus dan coba restart jika perlu."
            )
    finally:
        if own_db:
            db.close()

    return health
