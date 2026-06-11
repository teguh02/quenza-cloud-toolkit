"""Schedule service: per-project schedule management and destination linking."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Destination, Project, Schedule

_VALID_FREQ = {"daily", "weekly", "monthly"}


def list_schedules(db: Session) -> list[Schedule]:
    """Return all schedules joined with their projects."""
    stmt = select(Schedule).order_by(Schedule.updated_at.desc())
    return list(db.scalars(stmt).all())


def get_for_project(db: Session, project_id: int) -> Schedule | None:
    """Return the schedule for a project, or None."""
    stmt = select(Schedule).where(Schedule.project_id == project_id)
    return db.scalars(stmt).one_or_none()


def set_schedule(
    db: Session,
    project_id: int,
    *,
    enabled: bool,
    frequency: str,
    hour: int,
    minute: int,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
) -> Schedule:
    """Create or update a project's schedule.

    Raises:
        ValueError: on validation errors or missing project.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project tidak ditemukan.")

    freq = (frequency or "daily").lower()
    if freq not in _VALID_FREQ:
        raise ValueError("Frekuensi tidak valid (daily/weekly/monthly).")

    if not (0 <= hour <= 23):
        raise ValueError("Jam harus antara 0-23.")
    if not (0 <= minute <= 59):
        raise ValueError("Menit harus antara 0-59.")

    if freq == "weekly":
        if day_of_week is None or not (0 <= day_of_week <= 6):
            raise ValueError("Hari dalam minggu harus 0 (Senin) - 6 (Minggu).")
        day_of_month = None
    elif freq == "monthly":
        if day_of_month is None or not (1 <= day_of_month <= 31):
            raise ValueError("Tanggal harus antara 1-31.")
        day_of_week = None
    else:  # daily
        day_of_week = None
        day_of_month = None

    sched = get_for_project(db, project_id)
    if sched is None:
        sched = Schedule(project_id=project_id)
        db.add(sched)

    sched.is_enabled = bool(enabled)
    sched.frequency = freq
    sched.hour = hour
    sched.minute = minute
    sched.day_of_week = day_of_week
    sched.day_of_month = day_of_month

    db.commit()
    db.refresh(sched)
    return sched


def describe(sched: Schedule | None) -> str:
    """Return a human-readable description of a schedule."""
    if sched is None or not sched.is_enabled:
        return "Tidak dijadwalkan"
    days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    t = f"{sched.hour:02d}:{sched.minute:02d}"
    if sched.frequency == "weekly":
        d = days[sched.day_of_week] if sched.day_of_week is not None else "Senin"
        return f"Setiap {d}, {t}"
    if sched.frequency == "monthly":
        return f"Tanggal {sched.day_of_month or 1} setiap bulan, {t}"
    return f"Setiap hari, {t}"


# --- Destination linking (selective per project) ----------------------------


def set_project_destinations(
    db: Session, project_id: int, destination_ids: list[int]
) -> Project:
    """Replace a project's destination links with the given set.

    Raises:
        ValueError: if the project does not exist.
    """
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project tidak ditemukan.")

    if destination_ids:
        stmt = select(Destination).where(Destination.id.in_(destination_ids))
        destinations = list(db.scalars(stmt).all())
    else:
        destinations = []

    project.destinations = destinations
    db.commit()
    db.refresh(project)
    return project
