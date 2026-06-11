"""Dashboard data service (Phase 5: backed by real database data).

Aggregates live data from Projects, Destinations, Schedules, and
BackupLog rows into the structures the dashboard template expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BackupLog,
    Destination,
    Project,
    Schedule,
)
from app.services import log_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}".strip()
        num /= 1024.0
    return f"{num:.1f} PB"


def _relative_time(dt: datetime | None) -> str:
    """Return a short relative time like '12m lalu'."""
    if dt is None:
        return "-"
    now = _utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return "baru saja"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m lalu"
    hours = mins // 60
    if hours < 24:
        return f"{hours} jam lalu"
    days = hours // 24
    if days == 1:
        return "kemarin"
    return f"{days} hari lalu"


@dataclass(frozen=True)
class StatCard:
    key: str
    label: str
    value: str
    hint: str
    icon: str
    tone: str
    fg: str
    trend: str | None = None
    trend_up: bool = True


@dataclass(frozen=True)
class ActivityItem:
    title: str
    detail: str
    status: str
    timestamp: str


def get_stat_cards(db: Session) -> list[StatCard]:
    """Build the six headline statistic cards from live data."""
    total_projects = int(db.scalar(select(func.count(Project.id))) or 0)
    active_destinations = int(
        db.scalar(select(func.count(Destination.id)).where(Destination.is_active.is_(True)))
        or 0
    )

    counts = log_service.summary_counts(db)
    success = counts["backup_success"]
    failed = counts["backup_failed"]
    total_backups = success + failed + counts["backup_partial"]
    rate = f"{(success / total_backups * 100):.1f}%" if total_backups else "-"

    # Storage used = sum of successful backup archive sizes.
    total_size = int(
        db.scalar(
            select(func.coalesce(func.sum(BackupLog.size_bytes), 0)).where(
                BackupLog.action == "backup", BackupLog.status == "success"
            )
        )
        or 0
    )

    # Next scheduled backup.
    next_sched = db.scalars(
        select(Schedule)
        .where(Schedule.is_enabled.is_(True), Schedule.next_run_at.is_not(None))
        .order_by(Schedule.next_run_at.asc())
        .limit(1)
    ).first()
    if next_sched and next_sched.next_run_at:
        next_value = next_sched.next_run_at.strftime("%d %b %H:%M")
        next_hint = next_sched.project.name if next_sched.project else "Terjadwal"
    else:
        next_value = "-"
        next_hint = "Belum ada jadwal aktif"

    last = log_service.last_activity(db)
    last_value = _relative_time(last.created_at) if last else "-"
    last_hint = (last.message[:40] if last else "Belum ada aktivitas")

    return [
        StatCard(
            key="total_projects", label="Total Projects", value=str(total_projects),
            hint="Workspace tersimpan", icon="folder", tone="pastel-blue", fg="text-blue-500",
        ),
        StatCard(
            key="next_backup", label="Next Scheduled Backup", value=next_value,
            hint=next_hint, icon="clock", tone="pastel-green", fg="text-brand-teal",
        ),
        StatCard(
            key="storage_used", label="Storage Used", value=_human_size(total_size),
            hint="Total arsip sukses", icon="cloud", tone="pastel-purple", fg="text-purple-500",
        ),
        StatCard(
            key="active_destinations", label="Active Destinations", value=str(active_destinations),
            hint="Destinasi aktif", icon="cloud", tone="pastel-orange", fg="text-amber-500",
        ),
        StatCard(
            key="backups_result", label="Successful / Failed", value=f"{success} / {failed}",
            hint="Semua waktu", icon="list", tone="pastel-green", fg="text-brand-teal",
            trend=rate if total_backups else None, trend_up=True,
        ),
        StatCard(
            key="last_activity", label="Last Activity", value=last_value,
            hint=last_hint, icon="grid", tone="pastel-blue", fg="text-blue-500",
        ),
    ]


def get_backup_trend(db: Session, days: int = 7) -> dict:
    """Return labelled success/failed counts for the trend chart."""
    return log_service.trend(db, days)


def get_recent_activity(db: Session, limit: int = 6) -> list[ActivityItem]:
    """Return recent activity from BackupLog."""
    logs = log_service.recent(db, limit)
    items: list[ActivityItem] = []
    for log in logs:
        if log.action == "restore":
            title = "Restore selesai" if log.status == "success" else "Restore gagal"
        elif log.status == "success":
            title = "Backup berhasil"
        elif log.status == "partial":
            title = "Backup sebagian"
        else:
            title = "Backup gagal"
        items.append(
            ActivityItem(
                title=title,
                detail=log.message or (log.project_name or ""),
                status=log.status if log.status in ("success", "failed", "partial") else "info",
                timestamp=_relative_time(log.created_at),
            )
        )
    return items


def get_quick_actions() -> list[dict[str, str]]:
    """Return Quick Actions shortcuts shown on the dashboard."""
    return [
        {"label": "New Project", "desc": "Buat workspace backup", "href": "/projects", "icon": "folder", "tone": "pastel-blue", "fg": "text-blue-500"},
        {"label": "Run Backup", "desc": "Eksekusi backup manual", "href": "/projects", "icon": "cloud", "tone": "pastel-green", "fg": "text-brand-teal"},
        {"label": "Add Schedule", "desc": "Atur jadwal otomatis", "href": "/schedules", "icon": "clock", "tone": "pastel-orange", "fg": "text-amber-500"},
        {"label": "Restore", "desc": "Pulihkan dari backup", "href": "/restore", "icon": "list", "tone": "pastel-purple", "fg": "text-purple-500"},
    ]
