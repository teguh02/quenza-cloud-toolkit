"""Notification service: send backup/restore notifications via email/telegram.

Reads the active channel from settings_service and dispatches a message.
All sending is best-effort: failures never raise to the caller (they are
logged), so a notification problem cannot fail a backup/restore.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.services import settings_service

logger = logging.getLogger("quenza.notify")

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 20


# --- Low-level transports ---------------------------------------------------


def send_email(subject: str, body: str, recipients: list[str]) -> tuple[bool, str]:
    """Send a plaintext email via the configured SMTP server."""
    cfg = settings_service.get_notification_config().smtp
    if not cfg.is_complete:
        return False, "Konfigurasi SMTP belum lengkap."
    if not recipients:
        return False, "Tidak ada penerima email."

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        if cfg.use_tls:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=_TIMEOUT) as server:
                server.starttls()
                if cfg.user and cfg.password:
                    server.login(cfg.user, cfg.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=_TIMEOUT) as server:
                if cfg.user and cfg.password:
                    server.login(cfg.user, cfg.password)
                server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Email notification failed: %s", exc)
        return False, f"Gagal mengirim email: {exc}"

    return True, "Email terkirim."


def send_telegram(text: str) -> tuple[bool, str]:
    """Send a message via the Telegram Bot API."""
    cfg = settings_service.get_notification_config().telegram
    if not cfg.is_complete:
        return False, "Konfigurasi Telegram belum lengkap."

    try:
        import httpx

        url = _TELEGRAM_API.format(token=cfg.token)
        resp = httpx.post(
            url,
            json={"chat_id": cfg.chat_id, "text": text, "parse_mode": "HTML"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            detail = ""
            try:
                detail = resp.json().get("description", "")
            except Exception:  # pragma: no cover
                detail = resp.text[:120]
            return False, f"Telegram menolak: {detail or resp.status_code}"
    except ImportError:  # pragma: no cover
        return False, "Library 'httpx' belum terpasang."
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)
        return False, f"Gagal mengirim Telegram: {exc}"

    return True, "Pesan Telegram terkirim."


# --- Test helper (used by Settings page) ------------------------------------


def send_test() -> tuple[bool, str]:
    """Send a test message via the currently active channel."""
    cfg = settings_service.get_notification_config()
    subject = "Quenza Cloud Toolkit — Tes Notifikasi"
    body = (
        "Ini adalah pesan tes dari Quenza Cloud Toolkit.\n\n"
        "Jika Anda menerima pesan ini, konfigurasi notifikasi Anda sudah benar."
    )
    if cfg.channel == "email":
        return send_email(subject, body, cfg.recipients)
    if cfg.channel == "telegram":
        return send_telegram(
            "<b>Quenza Cloud Toolkit</b>\nTes notifikasi berhasil. "
            "Konfigurasi Telegram Anda sudah benar."
        )
    return False, "Tidak ada channel notifikasi aktif."


# --- High-level event notifications -----------------------------------------


def _status_label(status: str) -> str:
    return {
        "success": "BERHASIL",
        "partial": "SEBAGIAN",
        "failed": "GAGAL",
    }.get(status, status.upper())


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}".strip()
        num /= 1024.0
    return f"{num:.1f} PB"


def _should_notify(cfg: settings_service.NotificationConfig, status: str) -> bool:
    if cfg.channel == "none":
        return False
    if cfg.notify_on == "failed" and status == "success":
        return False
    return True


def notify_backup_result(result: dict, project_name: str = "") -> None:
    """Notify about a backup result (best-effort)."""
    try:
        cfg = settings_service.get_notification_config()
        status = result.get("status", "failed")
        if not _should_notify(cfg, status):
            return

        label = _status_label(status)
        size = _human_size(result.get("size_bytes", 0) or 0)
        dur = f"{(result.get('duration_ms', 0) or 0) / 1000:.1f}s"
        name = project_name or "(project)"
        when = settings_service.to_local(_now())

        subject = f"[Quenza] Backup {label}: {name}"
        lines = [
            f"Project : {name}",
            f"Status  : {label}",
            f"Pesan   : {result.get('message', '')}",
            f"Arsip   : {result.get('archive_name', '-') or '-'}",
            f"Ukuran  : {size}",
            f"Durasi  : {dur}",
            f"Waktu   : {when.strftime('%Y-%m-%d %H:%M %Z') if when else '-'}",
        ]
        body = "\n".join(lines)

        if cfg.channel == "email":
            send_email(subject, body, cfg.recipients)
        elif cfg.channel == "telegram":
            emoji = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(status, "ℹ️")
            html = (
                f"{emoji} <b>Backup {label}</b>\n"
                f"<b>Project:</b> {name}\n"
                f"<b>Pesan:</b> {result.get('message', '')}\n"
                f"<b>Arsip:</b> {result.get('archive_name', '-') or '-'}\n"
                f"<b>Ukuran:</b> {size} · <b>Durasi:</b> {dur}"
            )
            send_telegram(html)
    except Exception:  # pragma: no cover - never break the caller
        logger.exception("notify_backup_result failed")


def notify_restore_result(result: dict, source_name: str = "") -> None:
    """Notify about a restore result (best-effort)."""
    try:
        cfg = settings_service.get_notification_config()
        status = result.get("status", "failed")
        if not _should_notify(cfg, status):
            return

        label = _status_label(status)
        detail = result.get("detail", {}) or {}
        target = detail.get("target", "-")
        archive = detail.get("archive", "-")
        name = source_name or detail.get("destination", "(destinasi)")

        subject = f"[Quenza] Restore {label}"
        body = "\n".join([
            f"Status  : {label}",
            f"Sumber  : {name}",
            f"Arsip   : {archive}",
            f"Tujuan  : {target}",
            f"Pesan   : {result.get('message', '')}",
        ])

        if cfg.channel == "email":
            send_email(subject, body, cfg.recipients)
        elif cfg.channel == "telegram":
            emoji = {"success": "✅", "failed": "❌"}.get(status, "ℹ️")
            html = (
                f"{emoji} <b>Restore {label}</b>\n"
                f"<b>Sumber:</b> {name}\n"
                f"<b>Arsip:</b> {archive}\n"
                f"<b>Tujuan:</b> {target}\n"
                f"<b>Pesan:</b> {result.get('message', '')}"
            )
            send_telegram(html)
    except Exception:  # pragma: no cover
        logger.exception("notify_restore_result failed")


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)
