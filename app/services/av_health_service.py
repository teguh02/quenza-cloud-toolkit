"""Antivirus & Scanner health monitoring service.

Proactively checks the state of the dual-engine antivirus system (ClamAV
+ YARA) and reports on readiness, configuration, performance metrics, and
potential issues. Results are consumed by the Dashboard and Security page
to show alert banners when problems are detected.

Checks performed:
  * ClamAV binary availability (clamdscan / clamscan in PATH)
  * ClamAV daemon status (clamd process running)
  * YARA module availability and rule compilation state
  * YARA rules directory and file count
  * Antivirus feature enabled/disabled in AppSettings
  * Scan target directories configured and accessible
  * Last scan result and time elapsed since last scan
  * Quarantine directory status
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AppSetting, BackupLog, QuarantineLog

logger = logging.getLogger("quenza.av_health")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EngineStatus:
    """Status of a single scan engine."""

    name: str
    available: bool = False
    detail: str = ""


@dataclass
class LastScanInfo:
    """Summary of the most recent scan."""

    ran_at: datetime | None = None
    status: str = ""
    files_scanned: int = 0
    threats_found: int = 0
    duration_ms: int = 0
    hours_ago: float = 0.0


@dataclass
class AntivirusHealth:
    """Result of a full antivirus health check."""

    is_healthy: bool = True
    av_enabled: bool = False
    engines: list[EngineStatus] = field(default_factory=list)
    any_engine_available: bool = False
    targets_configured: int = 0
    targets_accessible: int = 0
    inaccessible_targets: list[str] = field(default_factory=list)
    yara_rules_count: int = 0
    quarantine_count: int = 0
    last_scan: LastScanInfo | None = None
    alerts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine checks
# ---------------------------------------------------------------------------

def _check_clamav() -> EngineStatus:
    """Check ClamAV binary availability and daemon status."""
    scanner_bin = shutil.which("clamdscan") or shutil.which("clamscan")
    if not scanner_bin:
        return EngineStatus(
            name="ClamAV",
            available=False,
            detail="Binary clamscan/clamdscan tidak ditemukan di PATH.",
        )

    # Check if clamd is running (best-effort — only on Linux).
    daemon_running = True
    if platform.system() != "Windows":
        try:
            import psutil

            clamd_procs = [
                p
                for p in psutil.process_iter(["name"])
                if "clamd" in (p.info["name"] or "").lower()
            ]
            daemon_running = len(clamd_procs) > 0
        except Exception:
            # psutil not available or error — assume OK.
            daemon_running = True

    using = os.path.basename(scanner_bin)
    if using == "clamdscan" and not daemon_running:
        return EngineStatus(
            name="ClamAV",
            available=True,
            detail=f"Binary: {using} (daemon clamd tidak aktif — scan mungkin gagal).",
        )

    return EngineStatus(
        name="ClamAV",
        available=True,
        detail=f"Binary: {using}" + (" (daemon clamd aktif)" if daemon_running and using == "clamdscan" else ""),
    )


def _check_yara() -> tuple[EngineStatus, int]:
    """Check YARA availability and rule count."""
    try:
        import yara  # noqa: F401
    except ImportError:
        return EngineStatus(
            name="YARA",
            available=False,
            detail="Module yara-python tidak terpasang.",
        ), 0

    rules_dir = os.path.join("app", "data", "yara_rules")
    if not os.path.isdir(rules_dir):
        return EngineStatus(
            name="YARA",
            available=False,
            detail=f"Direktori rules tidak ditemukan: {rules_dir}",
        ), 0

    # Count .yar files.
    rule_count = 0
    for root, _, files in os.walk(rules_dir):
        for f in files:
            if f.endswith(".yar"):
                rule_count += 1

    if rule_count == 0:
        return EngineStatus(
            name="YARA",
            available=False,
            detail="Tidak ada file rules (*.yar) ditemukan.",
        ), 0

    # Check if rules are already compiled (lazy global in scanner_service).
    compiled = False
    try:
        from app.services.scanner_service import _COMPILED_RULES, _YARA_DISABLED

        if _COMPILED_RULES is not None:
            compiled = True
        elif _YARA_DISABLED:
            return EngineStatus(
                name="YARA",
                available=False,
                detail=f"{rule_count} file rules ditemukan, tapi kompilasi gagal.",
            ), rule_count
    except ImportError:
        pass

    detail = f"{rule_count} file rules ditemukan"
    if compiled:
        detail += " (terkompilasi ✓)"

    return EngineStatus(name="YARA", available=True, detail=detail), rule_count


# ---------------------------------------------------------------------------
# Main health check
# ---------------------------------------------------------------------------

def get_health_status(db: Session | None = None) -> AntivirusHealth:
    """Run all antivirus health checks and return an AntivirusHealth report."""
    health = AntivirusHealth()

    # --- Engine checks ------------------------------------------------------
    clamav_status = _check_clamav()
    yara_status, yara_rules = _check_yara()

    health.engines = [clamav_status, yara_status]
    health.any_engine_available = clamav_status.available or yara_status.available
    health.yara_rules_count = yara_rules

    # --- DB checks ----------------------------------------------------------
    own_db = db is None
    if own_db:
        db = SessionLocal()

    try:
        # AV enabled setting.
        av_setting = db.scalars(
            select(AppSetting).where(AppSetting.key == "av_enabled")
        ).first()
        health.av_enabled = bool(av_setting and av_setting.value == "1")

        # Scan targets.
        targets_setting = db.scalars(
            select(AppSetting).where(AppSetting.key == "av_targets")
        ).first()
        targets: list[str] = []
        if targets_setting and targets_setting.value:
            try:
                import json

                targets = json.loads(targets_setting.value)
            except Exception:
                targets = []

        health.targets_configured = len(targets)
        for t in targets:
            if os.path.exists(t):
                health.targets_accessible += 1
            else:
                health.inaccessible_targets.append(t)

        # Quarantine count.
        quarantine_count = db.scalar(
            select(func.count(QuarantineLog.id)).where(
                QuarantineLog.status == "quarantined"
            )
        )
        health.quarantine_count = int(quarantine_count or 0)

        # Last scan.
        last_log = db.scalars(
            select(BackupLog)
            .where(BackupLog.action == "scan")
            .order_by(BackupLog.created_at.desc())
            .limit(1)
        ).first()

        if last_log:
            scan_info = LastScanInfo(
                ran_at=last_log.created_at,
                status=last_log.status or "",
                duration_ms=last_log.duration_ms or 0,
            )
            # Parse detail_json for file/threat counts.
            try:
                import json

                detail = json.loads(last_log.detail_json or "{}")
                scan_info.files_scanned = detail.get("total_files_scanned", 0)
                scan_info.threats_found = len(detail.get("findings", []))
            except Exception:
                pass

            # How long ago.
            if scan_info.ran_at:
                ran = scan_info.ran_at
                if ran.tzinfo is None:
                    ran = ran.replace(tzinfo=timezone.utc)
                delta = _utcnow() - ran
                scan_info.hours_ago = round(delta.total_seconds() / 3600, 1)

            health.last_scan = scan_info

    finally:
        if own_db:
            db.close()

    # --- Build alerts & warnings --------------------------------------------

    if not health.any_engine_available:
        health.is_healthy = False
        health.alerts.append(
            "Tidak ada mesin antivirus yang tersedia (ClamAV maupun YARA). "
            "Pemindaian malware tidak dapat berjalan."
        )

    if health.av_enabled and not health.any_engine_available:
        health.alerts.append(
            "Auto-scan terjadwal diaktifkan tapi tidak ada mesin yang siap. "
            "Scan terjadwal akan gagal."
        )

    if health.av_enabled and health.targets_configured == 0:
        health.warnings.append(
            "Auto-scan aktif tapi belum ada target direktori yang dikonfigurasi."
        )

    if health.inaccessible_targets:
        count = len(health.inaccessible_targets)
        names = ", ".join(health.inaccessible_targets[:3])
        suffix = f" dan {count - 3} lainnya" if count > 3 else ""
        health.warnings.append(
            f"{count} target direktori tidak dapat diakses: {names}{suffix}"
        )

    # Stale scan warning — if AV is enabled and last scan > 48 hours ago
    # (expected daily at 03:00), something may be wrong.
    if health.av_enabled and health.last_scan:
        if health.last_scan.hours_ago > 48:
            health.warnings.append(
                f"Scan terakhir sudah {health.last_scan.hours_ago:.0f} jam yang lalu. "
                "Pastikan scheduler berjalan normal."
            )
    elif health.av_enabled and health.last_scan is None:
        health.warnings.append(
            "Auto-scan aktif tapi belum pernah ada scan yang tercatat. "
            "Jalankan scan manual untuk verifikasi."
        )

    # ClamAV daemon warning.
    for eng in health.engines:
        if eng.name == "ClamAV" and eng.available and "daemon clamd tidak aktif" in eng.detail:
            health.warnings.append(
                "ClamAV daemon (clamd) tidak aktif. clamdscan mungkin gagal. "
                "Jalankan: sudo systemctl start clamav-daemon"
            )

    # Quarantine alert.
    if health.quarantine_count > 0:
        health.warnings.append(
            f"{health.quarantine_count} file masih di-karantina dan menunggu tindakan (restore/hapus)."
        )

    # If there are critical alerts, mark unhealthy.
    if health.alerts:
        health.is_healthy = False

    return health
