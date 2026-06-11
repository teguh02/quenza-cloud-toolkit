"""Application settings service: timezone & notification configuration.

Settings are persisted in the `app_settings` table as key/value rows.
Structured values are JSON-encoded; sensitive values (SMTP password,
Telegram bot token) are encrypted via app.services.crypto.

A small in-process cache avoids a DB hit on every request; it is
invalidated whenever settings are written.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AppSetting
from app.services import crypto

# --- Keys -------------------------------------------------------------------
KEY_TIMEZONE = "timezone"
KEY_NOTIFY_CHANNEL = "notify_channel"      # none | email | telegram
KEY_NOTIFY_ON = "notify_on"                # all | failed
KEY_SMTP = "smtp"                          # JSON: host, port, user, password(enc), from_addr, use_tls
KEY_EMAIL_RECIPIENTS = "email_recipients"  # JSON list[str]
KEY_TELEGRAM = "telegram"                  # JSON: token(enc), chat_id

DEFAULT_TIMEZONE = "Asia/Jakarta"
MAX_RECIPIENTS = 3

# A curated shortlist shown first in the dropdown (full list also available).
COMMON_TIMEZONES = [
    "UTC",
    "Asia/Jakarta",
    "Asia/Makassar",
    "Asia/Jayapura",
    "Asia/Singapore",
    "Asia/Kuala_Lumpur",
    "Asia/Bangkok",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Asia/Dubai",
    "Europe/London",
    "Europe/Paris",
    "America/New_York",
    "America/Los_Angeles",
    "Australia/Sydney",
]

# Module-level cache of key -> raw value.
_cache: dict[str, str] | None = None


# --- Low-level get/set ------------------------------------------------------


def _load_all(db: Session) -> dict[str, str]:
    rows = db.scalars(select(AppSetting)).all()
    return {r.key: r.value for r in rows}


def _ensure_cache() -> dict[str, str]:
    global _cache
    if _cache is None:
        db = SessionLocal()
        try:
            _cache = _load_all(db)
        finally:
            db.close()
    return _cache


def invalidate_cache() -> None:
    """Clear the in-process settings cache."""
    global _cache
    _cache = None


def _get_raw(key: str, default: str = "") -> str:
    return _ensure_cache().get(key, default)


def _set_raw(db: Session, key: str, value: str) -> None:
    row = db.scalars(select(AppSetting).where(AppSetting.key == key)).one_or_none()
    if row is None:
        row = AppSetting(key=key, value=value)
        db.add(row)
    else:
        row.value = value


# --- Timezone ---------------------------------------------------------------


def get_timezone_name() -> str:
    """Return the configured timezone name (defaults to DEFAULT_TIMEZONE)."""
    return _get_raw(KEY_TIMEZONE, DEFAULT_TIMEZONE) or DEFAULT_TIMEZONE


def get_tzinfo() -> tzinfo:
    """Return a tzinfo for the configured timezone (falls back to UTC)."""
    try:
        return ZoneInfo(get_timezone_name())
    except Exception:
        return timezone.utc


def is_valid_timezone(name: str) -> bool:
    """Return True if `name` is a valid IANA timezone."""
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except Exception:
        return False


def to_local(dt: datetime | None) -> datetime | None:
    """Convert a (UTC) datetime to the configured local timezone."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(get_tzinfo())


def set_timezone(db: Session, name: str) -> None:
    """Persist the timezone. Raises ValueError if invalid."""
    name = (name or "").strip()
    if not is_valid_timezone(name):
        raise ValueError("Zona waktu tidak valid.")
    _set_raw(db, KEY_TIMEZONE, name)
    db.commit()
    invalidate_cache()


def all_timezones() -> list[str]:
    """Return the full sorted list of IANA timezones."""
    return sorted(available_timezones())


# --- Notification config (structured) ---------------------------------------


@dataclass
class SmtpConfig:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""       # plaintext in-memory; encrypted at rest
    from_addr: str = ""
    use_tls: bool = True

    @property
    def is_complete(self) -> bool:
        return bool(self.host and self.port and self.from_addr)


@dataclass
class TelegramConfig:
    token: str = ""          # plaintext in-memory; encrypted at rest
    chat_id: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.token and self.chat_id)


@dataclass
class NotificationConfig:
    channel: str = "none"        # none | email | telegram
    notify_on: str = "all"       # all | failed
    smtp: SmtpConfig = field(default_factory=SmtpConfig)
    recipients: list[str] = field(default_factory=list)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


def _decrypt_safe(value: str) -> str:
    try:
        return crypto.decrypt(value)
    except crypto.CryptoNotConfigured:
        return ""


def get_notification_config() -> NotificationConfig:
    """Build the current NotificationConfig from stored settings."""
    cfg = NotificationConfig(
        channel=_get_raw(KEY_NOTIFY_CHANNEL, "none") or "none",
        notify_on=_get_raw(KEY_NOTIFY_ON, "all") or "all",
    )

    # SMTP
    try:
        smtp_raw = json.loads(_get_raw(KEY_SMTP, "{}") or "{}")
    except json.JSONDecodeError:
        smtp_raw = {}
    cfg.smtp = SmtpConfig(
        host=smtp_raw.get("host", ""),
        port=int(smtp_raw.get("port", 587) or 587),
        user=smtp_raw.get("user", ""),
        password=_decrypt_safe(smtp_raw.get("password", "")) if smtp_raw.get("password") else "",
        from_addr=smtp_raw.get("from_addr", ""),
        use_tls=bool(smtp_raw.get("use_tls", True)),
    )

    # Recipients
    try:
        cfg.recipients = json.loads(_get_raw(KEY_EMAIL_RECIPIENTS, "[]") or "[]")
    except json.JSONDecodeError:
        cfg.recipients = []

    # Telegram
    try:
        tg_raw = json.loads(_get_raw(KEY_TELEGRAM, "{}") or "{}")
    except json.JSONDecodeError:
        tg_raw = {}
    cfg.telegram = TelegramConfig(
        token=_decrypt_safe(tg_raw.get("token", "")) if tg_raw.get("token") else "",
        chat_id=tg_raw.get("chat_id", ""),
    )
    return cfg


def _parse_recipients(raw: str) -> list[str]:
    """Split a comma/newline-separated string into a clean email list."""
    if not raw:
        return []
    parts = [p.strip() for chunk in raw.replace("\n", ",").split(",") for p in [chunk]]
    return [p for p in parts if p]


def _valid_email(addr: str) -> bool:
    # Lightweight check; full RFC validation is out of scope.
    return "@" in addr and "." in addr.split("@")[-1] and len(addr) <= 254


def save_notifications(
    db: Session,
    *,
    channel: str,
    notify_on: str = "all",
    # email
    smtp_host: str = "",
    smtp_port: str = "587",
    smtp_user: str = "",
    smtp_password: str = "",
    smtp_from: str = "",
    smtp_use_tls: bool = True,
    recipients_raw: str = "",
    # telegram
    telegram_token: str = "",
    telegram_chat_id: str = "",
    keep_existing_secrets: bool = True,
) -> None:
    """Validate and persist notification settings.

    For secret fields (smtp_password, telegram_token), an empty submitted
    value preserves the previously stored secret when keep_existing_secrets
    is True (so users don't have to retype secrets to edit other fields).

    Raises:
        ValueError: on validation problems.
    """
    channel = (channel or "none").strip().lower()
    if channel not in ("none", "email", "telegram"):
        raise ValueError("Channel notifikasi tidak valid.")
    notify_on = (notify_on or "all").strip().lower()
    if notify_on not in ("all", "failed"):
        notify_on = "all"

    existing = get_notification_config()

    if channel == "email":
        host = smtp_host.strip()
        from_addr = smtp_from.strip()
        if not host:
            raise ValueError("SMTP host wajib diisi untuk notifikasi email.")
        if not from_addr:
            raise ValueError("Alamat pengirim (from) wajib diisi.")
        try:
            port = int(str(smtp_port).strip() or "587")
        except ValueError:
            raise ValueError("Port SMTP harus berupa angka.") from None

        recipients = _parse_recipients(recipients_raw)
        if not recipients:
            raise ValueError("Tambahkan minimal satu email penerima.")
        if len(recipients) > MAX_RECIPIENTS:
            raise ValueError(f"Maksimal {MAX_RECIPIENTS} email penerima.")
        for r in recipients:
            if not _valid_email(r):
                raise ValueError(f"Email tidak valid: {r}")

        # Resolve password (keep existing if blank).
        password = smtp_password
        if not password and keep_existing_secrets:
            password = existing.smtp.password

        smtp_obj = {
            "host": host,
            "port": port,
            "user": smtp_user.strip(),
            "from_addr": from_addr,
            "use_tls": bool(smtp_use_tls),
        }
        if password:
            try:
                smtp_obj["password"] = crypto.encrypt(password)
            except crypto.CryptoNotConfigured as exc:
                raise ValueError(str(exc)) from exc
        else:
            smtp_obj["password"] = ""

        _set_raw(db, KEY_SMTP, json.dumps(smtp_obj, ensure_ascii=False))
        _set_raw(db, KEY_EMAIL_RECIPIENTS, json.dumps(recipients, ensure_ascii=False))

    elif channel == "telegram":
        chat_id = telegram_chat_id.strip()
        token = telegram_token.strip()
        if not token and keep_existing_secrets:
            token = existing.telegram.token
        if not token:
            raise ValueError("Bot token Telegram wajib diisi.")
        if not chat_id:
            raise ValueError("Chat ID Telegram wajib diisi.")

        tg_obj = {"chat_id": chat_id}
        try:
            tg_obj["token"] = crypto.encrypt(token)
        except crypto.CryptoNotConfigured as exc:
            raise ValueError(str(exc)) from exc
        _set_raw(db, KEY_TELEGRAM, json.dumps(tg_obj, ensure_ascii=False))

    _set_raw(db, KEY_NOTIFY_CHANNEL, channel)
    _set_raw(db, KEY_NOTIFY_ON, notify_on)
    db.commit()
    invalidate_cache()
