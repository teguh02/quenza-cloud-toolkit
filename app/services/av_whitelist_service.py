"""Service for Antivirus filename whitelist CRUD + matching."""

from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AntivirusWhitelist


MAX_FILENAME_LENGTH = 255


def normalize_file_name(file_name: str) -> str:
    """Normalize a user-provided filename to a safe basename."""
    clean = (file_name or "").strip().replace("\\", "/")
    clean = os.path.basename(clean)
    return clean


def list_entries(db: Session) -> list[AntivirusWhitelist]:
    """Return all whitelist entries sorted alphabetically."""
    stmt = select(AntivirusWhitelist).order_by(
        func.lower(AntivirusWhitelist.file_name), AntivirusWhitelist.id
    )
    return db.scalars(stmt).all()


def create_entry(db: Session, file_name: str) -> AntivirusWhitelist:
    """Create a new whitelist entry with duplicate validation."""
    normalized = normalize_file_name(file_name)
    if not normalized:
        raise ValueError("Nama file wajib diisi.")
    if len(normalized) > MAX_FILENAME_LENGTH:
        raise ValueError(f"Nama file maksimal {MAX_FILENAME_LENGTH} karakter.")

    if _exists(db, normalized):
        raise ValueError("Nama file sudah ada pada daftar putih.")

    row = AntivirusWhitelist(file_name=normalized)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_entry(db: Session, entry_id: int, file_name: str) -> AntivirusWhitelist:
    """Update an existing whitelist entry."""
    row = db.get(AntivirusWhitelist, entry_id)
    if row is None:
        raise ValueError("Data daftar putih tidak ditemukan.")

    normalized = normalize_file_name(file_name)
    if not normalized:
        raise ValueError("Nama file wajib diisi.")
    if len(normalized) > MAX_FILENAME_LENGTH:
        raise ValueError(f"Nama file maksimal {MAX_FILENAME_LENGTH} karakter.")

    if _exists(db, normalized, exclude_id=entry_id):
        raise ValueError("Nama file sudah ada pada daftar putih.")

    row.file_name = normalized
    db.commit()
    db.refresh(row)
    return row


def delete_entry(db: Session, entry_id: int) -> None:
    """Delete a whitelist entry by id."""
    row = db.get(AntivirusWhitelist, entry_id)
    if row is None:
        raise ValueError("Data daftar putih tidak ditemukan.")
    db.delete(row)
    db.commit()


def get_filename_set(db: Session) -> set[str]:
    """Return normalized lowercase whitelist names for fast lookups."""
    stmt = select(AntivirusWhitelist.file_name)
    rows = db.scalars(stmt).all()
    return {normalize_file_name(name).lower() for name in rows if normalize_file_name(name)}


def is_whitelisted_path(file_path: str, white_set: set[str]) -> bool:
    """Check whether a file path basename exists in whitelist set."""
    if not white_set:
        return False
    file_name = normalize_file_name(file_path).lower()
    return bool(file_name and file_name in white_set)


def _exists(db: Session, file_name: str, exclude_id: int | None = None) -> bool:
    stmt = select(AntivirusWhitelist.id).where(
        func.lower(AntivirusWhitelist.file_name) == file_name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(AntivirusWhitelist.id != exclude_id)
    return db.scalars(stmt.limit(1)).first() is not None
