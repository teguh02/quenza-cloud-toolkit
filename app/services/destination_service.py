"""Destination service: CRUD for destinations and connection testing."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Destination, DestinationType
from app.services import crypto
from app.services.destinations import get_adapter
from app.services.destinations.registry import get_spec


def list_destinations(db: Session) -> list[Destination]:
    """Return all destinations, newest first."""
    stmt = select(Destination).order_by(Destination.created_at.desc())
    return list(db.scalars(stmt).all())


def get_destination(db: Session, dest_id: int) -> Destination | None:
    """Return a destination by id, or None."""
    return db.get(Destination, dest_id)


def _parse_type(value: str) -> DestinationType:
    try:
        return DestinationType(value)
    except ValueError:
        raise ValueError("Tipe destinasi tidak valid.") from None


def _spec_secret_fields(dest_type: str) -> set[str]:
    """Return the set of field names marked secret for a destination type."""
    spec = get_spec(dest_type)
    if not spec:
        return set()
    return {f["name"] for f in spec["fields"] if f.get("secret")}


def _build_config(dest_type: str, form: dict, existing: dict | None = None) -> dict:
    """Build a destination config from a submitted form.

    Secret fields (marked `secret: True` in the spec) are encrypted at rest.
    On edit, an empty secret value preserves the previously stored (already
    encrypted) value so users don't need to retype secrets.

    Raises:
        ValueError: required field missing, or crypto not configured.
    """
    spec = get_spec(dest_type)
    if spec is None:
        raise ValueError("Tipe destinasi tidak dikenal.")
    existing = existing or {}
    config: dict = {}
    for field in spec["fields"]:
        name = field["name"]
        value = (form.get(name) or "").strip()
        is_secret = bool(field.get("secret"))

        if field.get("required") and not value and not (is_secret and existing.get(name)):
            raise ValueError(f"Field '{field['label']}' wajib diisi.")

        if is_secret:
            if value:
                try:
                    config[name] = crypto.encrypt(value)
                except crypto.CryptoNotConfigured as exc:
                    raise ValueError(str(exc)) from exc
            else:
                # Preserve previously stored secret (already encrypted) if any.
                config[name] = existing.get(name, "")
        else:
            config[name] = value
    return config


def create_destination(
    db: Session, *, name: str, dest_type: str, form: dict
) -> Destination:
    """Create a destination from a submitted form dict.

    Raises:
        ValueError: on validation errors.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Nama destinasi tidak boleh kosong.")

    dtype = _parse_type(dest_type)
    config = _build_config(dtype.value, form)

    dest = Destination(
        name=name,
        dest_type=dtype,
        config_json=json.dumps(config, ensure_ascii=False),
        is_active=True,
    )
    db.add(dest)
    db.commit()
    db.refresh(dest)
    return dest


def update_destination(
    db: Session, dest_id: int, *, name: str, form: dict
) -> Destination:
    """Update an existing destination's name and config.

    For OAuth-based destinations (e.g. Google Drive), secret fields such as
    refresh_token/email are preserved from the existing config (they are not
    part of the edit form).
    """
    dest = get_destination(db, dest_id)
    if dest is None:
        raise ValueError("Destinasi tidak ditemukan.")

    name = (name or "").strip()
    if not name:
        raise ValueError("Nama destinasi tidak boleh kosong.")

    existing = parse_config(dest)
    config = _build_config(dest.dest_type.value, form, existing=existing)

    # Preserve OAuth-only fields that are not part of any form (Drive).
    if dest.dest_type == DestinationType.GDRIVE:
        for keep in ("refresh_token", "email"):
            if existing.get(keep):
                config[keep] = existing[keep]

    dest.name = name
    dest.config_json = json.dumps(config, ensure_ascii=False)
    db.commit()
    db.refresh(dest)
    return dest


def create_gdrive_destination(
    db: Session, *, name: str, refresh_token: str, email: str, folder_id: str = ""
) -> Destination:
    """Create a Google Drive destination from an OAuth result.

    The refresh token is encrypted at rest. Raises ValueError on bad input.
    """
    from app.services import crypto

    name = (name or "").strip() or (email or "Google Drive")
    if not refresh_token:
        raise ValueError("Refresh token kosong.")

    try:
        enc_token = crypto.encrypt(refresh_token)
    except crypto.CryptoNotConfigured as exc:
        raise ValueError(str(exc)) from exc

    config = {
        "refresh_token": enc_token,
        "email": (email or "").strip(),
        "folder_id": (folder_id or "").strip(),
    }
    dest = Destination(
        name=name,
        dest_type=DestinationType.GDRIVE,
        config_json=json.dumps(config, ensure_ascii=False),
        is_active=True,
    )
    db.add(dest)
    db.commit()
    db.refresh(dest)
    return dest


def delete_destination(db: Session, dest_id: int) -> bool:
    """Delete a destination. Returns True if removed."""
    dest = get_destination(db, dest_id)
    if dest is None:
        return False
    db.delete(dest)
    db.commit()
    return True


def test_destination(db: Session, dest_id: int) -> tuple[bool, str]:
    """Test a destination's connectivity. Returns (ok, message)."""
    dest = get_destination(db, dest_id)
    if dest is None:
        return False, "Destinasi tidak ditemukan."

    try:
        config = json.loads(dest.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    adapter = get_adapter(dest.dest_type.value, config)
    if adapter is None:
        return False, "Adapter destinasi tidak dikenal."

    result = adapter.test_connection()
    # Persist last status for display.
    dest.last_status = "ok" if result.ok else "error"
    db.commit()
    return result.ok, result.message


def parse_config(dest: Destination) -> dict:
    """Return the parsed config dict for a destination."""
    try:
        return json.loads(dest.config_json or "{}")
    except json.JSONDecodeError:
        return {}


def display_summary(dest: Destination) -> str:
    """Return a short, non-sensitive summary for list views."""
    cfg = parse_config(dest)
    t = dest.dest_type.value
    if t == "local":
        return cfg.get("path", "")
    if t == "s3":
        bucket = cfg.get("bucket", "")
        prefix = cfg.get("prefix", "")
        return f"s3://{bucket}/{prefix}".rstrip("/")
    if t == "gdrive":
        email = cfg.get("email", "")
        fid = cfg.get("folder_id", "")
        if email and fid:
            return f"{email} · folder {fid}"
        return email or (f"Folder: {fid}" if fid else "Google Drive")
    if t == "ftp":
        host = cfg.get("host", "")
        rd = cfg.get("remote_dir", "")
        return f"ftp://{host}/{rd.strip('/')}".rstrip("/")
    if t == "scp":
        host = cfg.get("host", "")
        user = cfg.get("user", "")
        rd = cfg.get("remote_dir", "")
        prefix = f"{user}@{host}" if user else host
        return f"{prefix}:{rd}" if rd else prefix
    return ""
