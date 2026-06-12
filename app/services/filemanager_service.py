"""File manager service: safe server-side directory browsing.

The Integrated File Manager lets users pick directories/files on the
server to add as backup sources. This module reads the filesystem with
strong error handling and returns plain dicts ready for JSON responses.

Design notes:
  * Cross-platform: on Windows, the "root" listing enumerates drives.
  * Listings never raise to the caller; permission/IO errors become a
    structured error payload instead.
  * Hidden entries (dotfiles) can be optionally included.
"""

from __future__ import annotations

import os
import shutil
import string
from datetime import datetime, timezone
from pathlib import Path


def _human_size(num: float) -> str:
    """Return a human-friendly byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}".strip()
        num /= 1024.0
    return f"{num:.1f} PB"


def _iso(ts: float) -> str:
    """Convert an epoch timestamp to an ISO-ish display string."""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


def list_windows_drives() -> list[dict]:
    """Enumerate available drive letters on Windows."""
    drives: list[dict] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            drives.append(
                {
                    "name": f"{letter}:",
                    "path": root,
                    "type": "directory",
                    "is_drive": True,
                    "size": "",
                    "modified": "",
                }
            )
    return drives


def _build_breadcrumb(path: Path) -> list[dict]:
    """Build breadcrumb segments from a resolved path."""
    parts: list[dict] = []
    # Anchor (drive root on Windows, "/" on POSIX)
    anchor = path.anchor or "/"
    parts.append({"name": anchor.replace("\\", "") or "/", "path": anchor})

    accumulated = Path(anchor)
    for segment in path.relative_to(anchor).parts:
        accumulated = accumulated / segment
        parts.append({"name": segment, "path": str(accumulated)})
    return parts


def browse(path: str | None = None, *, show_hidden: bool = False) -> dict:
    """List the contents of a directory.

    Args:
        path: Absolute directory path. If None/empty:
              - Windows: returns the drive list (virtual root).
              - POSIX: returns the contents of "/".
        show_hidden: include dotfiles / hidden entries.

    Returns:
        A dict with keys:
          ok (bool), path (str), is_root (bool), parent (str|None),
          breadcrumb (list), entries (list), error (str|None).
    """
    is_windows = os.name == "nt"

    # Virtual root on Windows -> show drives.
    if (not path) and is_windows:
        return {
            "ok": True,
            "path": "",
            "is_root": True,
            "parent": None,
            "breadcrumb": [{"name": "Drives", "path": ""}],
            "entries": list_windows_drives(),
            "error": None,
        }

    target = Path(path) if path else Path("/")

    try:
        target = target.resolve(strict=True)
    except (FileNotFoundError, RuntimeError, OSError):
        return _error(path or "", "Path tidak ditemukan atau tidak dapat diakses.")

    if not target.is_dir():
        return _error(str(target), "Path bukan sebuah direktori.")

    entries: list[dict] = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                name = entry.name
                if not show_hidden and name.startswith("."):
                    continue
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                    stat = entry.stat(follow_symlinks=False)
                    size = "" if is_dir else _human_size(stat.st_size)
                    modified = _iso(stat.st_mtime)
                except (OSError, PermissionError):
                    is_dir = False
                    size = ""
                    modified = ""

                entries.append(
                    {
                        "name": name,
                        "path": str(target / name),
                        "type": "directory" if is_dir else "file",
                        "is_drive": False,
                        "size": size,
                        "modified": modified,
                    }
                )
    except PermissionError:
        return _error(str(target), "Akses ditolak ke direktori ini.")
    except OSError as exc:
        return _error(str(target), f"Gagal membaca direktori: {exc.strerror or exc}")

    # Sort: directories first, then files; case-insensitive by name.
    entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))

    # Determine parent (None signals "go to root/drives").
    parent: str | None
    if target.parent == target:
        # Filesystem root reached.
        parent = "" if is_windows else None
    else:
        parent = str(target.parent)

    return {
        "ok": True,
        "path": str(target),
        "is_root": False,
        "parent": parent,
        "breadcrumb": _build_breadcrumb(target),
        "entries": entries,
        "error": None,
    }


def path_exists(path: str) -> tuple[bool, bool]:
    """Return (exists, is_dir) for a path, swallowing errors."""
    try:
        p = Path(path).resolve(strict=True)
        return True, p.is_dir()
    except (OSError, RuntimeError):
        return False, False


def _error(path: str, message: str) -> dict:
    """Build a structured error payload that the UI can render."""
    return {
        "ok": False,
        "path": path,
        "is_root": False,
        "parent": None,
        "breadcrumb": [],
        "entries": [],
        "error": message,
    }


def create_folder(path: str, name: str) -> dict:
    """Create a new folder inside the given absolute path."""
    try:
        target_dir = Path(path).resolve(strict=True)
        if not target_dir.is_dir():
            return _error(path, "Direktori induk tidak valid.")
        new_dir = target_dir / name
        new_dir.mkdir(parents=True, exist_ok=False)
        return {"ok": True, "path": str(new_dir)}
    except FileExistsError:
        return _error(path, "Direktori dengan nama tersebut sudah ada.")
    except (OSError, RuntimeError) as exc:
        return _error(path, f"Gagal membuat direktori: {exc}")


def create_file(path: str, name: str) -> dict:
    """Create an empty file inside the given absolute path."""
    try:
        target_dir = Path(path).resolve(strict=True)
        if not target_dir.is_dir():
            return _error(path, "Direktori induk tidak valid.")
        new_file = target_dir / name
        if new_file.exists():
            return _error(path, "File dengan nama tersebut sudah ada.")
        new_file.touch(exist_ok=False)
        return {"ok": True, "path": str(new_file)}
    except (OSError, RuntimeError) as exc:
        return _error(path, f"Gagal membuat file: {exc}")


def read_file_content(path: str) -> dict:
    """Read file content safely (max 1MB, utf-8 only)."""
    try:
        target = Path(path).resolve(strict=True)
        if not target.is_file():
            return _error(path, "Path bukan sebuah file.")
        if target.stat().st_size > 1024 * 1024:
            return _error(path, "Ukuran file melebihi batas 1MB.")
        content = target.read_text(encoding="utf-8")
        return {"ok": True, "content": content, "path": str(target)}
    except UnicodeDecodeError:
        return _error(path, "File biner tidak dapat diedit sebagai teks.")
    except (OSError, RuntimeError) as exc:
        return _error(path, f"Gagal membaca file: {exc}")


def write_file_content(path: str, content: str) -> dict:
    """Write text content back to a file."""
    try:
        target = Path(path).resolve(strict=True)
        if not target.is_file():
            return _error(path, "Path bukan sebuah file.")
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(target)}
    except (OSError, RuntimeError) as exc:
        return _error(path, f"Gagal menyimpan file: {exc}")


def delete_target(path: str) -> dict:
    """Delete a file or recursively delete a directory."""
    try:
        target = Path(path).resolve(strict=True)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True, "path": str(target)}
    except (OSError, RuntimeError) as exc:
        return _error(path, f"Gagal menghapus item: {exc}")
