"""Log service: query and summarize BackupLog rows for History/Logs and stats."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BackupLog

_PAGE_SIZE = 20


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def list_logs(
    db: Session,
    *,
    action: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = _PAGE_SIZE,
) -> dict:
    """Return a paginated, optionally filtered list of logs.

    Returns a dict: items, page, pages, total, has_prev, has_next.
    """
    page = max(1, page)

    stmt = select(BackupLog)
    count_stmt = select(func.count(BackupLog.id))

    if action in ("backup", "restore", "scan"):
        stmt = stmt.where(BackupLog.action == action)
        count_stmt = count_stmt.where(BackupLog.action == action)
    if status in ("success", "failed", "partial"):
        stmt = stmt.where(BackupLog.status == status)
        count_stmt = count_stmt.where(BackupLog.status == status)

    total = int(db.scalar(count_stmt) or 0)
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)

    stmt = (
        stmt.order_by(BackupLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(db.scalars(stmt).all())

    return {
        "items": items,
        "page": page,
        "pages": pages,
        "total": total,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


def get_log(db: Session, log_id: int) -> BackupLog | None:
    """Return a single log by id."""
    return db.get(BackupLog, log_id)


def parse_detail(log: BackupLog) -> dict:
    """Return the parsed detail_json for a log."""
    try:
        return json.loads(log.detail_json or "{}")
    except json.JSONDecodeError:
        return {}


def summary_counts(db: Session) -> dict:
    """Return overall counts used by dashboard and headers."""
    def _count(**filters) -> int:
        stmt = select(func.count(BackupLog.id))
        for k, v in filters.items():
            stmt = stmt.where(getattr(BackupLog, k) == v)
        return int(db.scalar(stmt) or 0)

    return {
        "total": _count(),
        "backup_success": _count(action="backup", status="success"),
        "backup_failed": _count(action="backup", status="failed"),
        "backup_partial": _count(action="backup", status="partial"),
        "restore_total": _count(action="restore"),
        "scan_total": _count(action="scan"),
    }


def trend(db: Session, days: int = 7) -> dict:
    """Return success/failed backup counts per day for the last `days`."""
    if days not in (7, 30):
        days = 7

    today = _utcnow().date()
    labels: list[str] = []
    success: list[int] = []
    failed: list[int] = []

    # Pull all backup logs in the window once, then bucket in Python
    # (simpler and DB-agnostic than date functions across engines).
    start = today - timedelta(days=days - 1)
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    stmt = select(BackupLog).where(
        BackupLog.action == "backup", BackupLog.created_at >= start_dt
    )
    rows = list(db.scalars(stmt).all())

    buckets: dict[str, dict[str, int]] = {}
    for i in range(days):
        day = start + timedelta(days=i)
        key = day.isoformat()
        buckets[key] = {"success": 0, "failed": 0}

    for row in rows:
        created = row.created_at
        if created is None:
            continue
        key = created.date().isoformat()
        if key not in buckets:
            continue
        if row.status == "success":
            buckets[key]["success"] += 1
        elif row.status in ("failed", "partial"):
            buckets[key]["failed"] += 1

    for i in range(days):
        day = start + timedelta(days=i)
        key = day.isoformat()
        labels.append(day.strftime("%d %b") if days <= 7 else day.strftime("%d/%m"))
        success.append(buckets[key]["success"])
        failed.append(buckets[key]["failed"])

    return {"labels": labels, "success": success, "failed": failed}


def recent(db: Session, limit: int = 6) -> list[BackupLog]:
    """Return the most recent logs."""
    stmt = select(BackupLog).order_by(BackupLog.created_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())


def last_activity(db: Session) -> BackupLog | None:
    """Return the single most recent log, or None."""
    stmt = select(BackupLog).order_by(BackupLog.created_at.desc()).limit(1)
    return db.scalars(stmt).first()
