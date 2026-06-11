"""Destination service: CRUD for destinations and connection testing."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Destination, DestinationType
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


def _build_config(dest_type: str, form: dict) -> dict:
    """Extract only the fields declared in the type's spec from a form."""
    spec = get_spec(dest_type)
    if spec is None:
        raise ValueError("Tipe destinasi tidak dikenal.")
    config: dict = {}
    for field in spec["fields"]:
        name = field["name"]
        value = (form.get(name) or "").strip()
        if field.get("required") and not value:
            raise ValueError(f"Field '{field['label']}' wajib diisi.")
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
    """Update an existing destination's name and config."""
    dest = get_destination(db, dest_id)
    if dest is None:
        raise ValueError("Destinasi tidak ditemukan.")

    name = (name or "").strip()
    if not name:
        raise ValueError("Nama destinasi tidak boleh kosong.")

    config = _build_config(dest.dest_type.value, form)
    dest.name = name
    dest.config_json = json.dumps(config, ensure_ascii=False)
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
        fid = cfg.get("folder_id", "")
        return f"Folder: {fid}" if fid else "Service Account"
    if t == "mega":
        return cfg.get("email", "")
    return ""
