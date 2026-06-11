"""Archive service: bundle multiple sources into a single zip/tar.gz.

Given a set of filesystem paths (directories and/or files) plus extra
"injected" files (e.g. database dumps), produce one compressed archive.
All filesystem access is wrapped so a single unreadable entry degrades
gracefully (it is skipped and reported) rather than aborting the archive.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArchiveItem:
    """A source to include in the archive.

    Attributes:
        path: Absolute path to a file or directory on disk.
        arcname: Top-level name to use inside the archive. Defaults to the
            basename of `path`.
    """

    path: str
    arcname: str | None = None


@dataclass
class ArchiveResult:
    """Outcome of an archive operation."""

    ok: bool
    output_path: str
    size_bytes: int = 0
    files_added: int = 0
    skipped: list[str] = field(default_factory=list)
    error: str | None = None


def _safe_arcname(item: ArchiveItem) -> str:
    """Return a clean top-level arcname for an item."""
    if item.arcname:
        return item.arcname.strip("/\\") or Path(item.path).name
    return Path(item.path).name


def create_archive(
    items: list[ArchiveItem],
    output_path: str,
    *,
    archive_format: str = "zip",
) -> ArchiveResult:
    """Create a compressed archive containing all items.

    Args:
        items: sources (directories/files) to include.
        output_path: full path of the archive to create (parent created).
        archive_format: "zip" or "tar.gz".

    Returns:
        ArchiveResult describing the outcome. Never raises for routine
        filesystem problems; unexpected errors are captured into `error`.
    """
    fmt = (archive_format or "zip").lower()
    if fmt not in ("zip", "tar.gz"):
        return ArchiveResult(
            ok=False, output_path=output_path, error=f"Format tidak didukung: {fmt}"
        )

    if not items:
        return ArchiveResult(
            ok=False, output_path=output_path, error="Tidak ada sumber untuk diarsipkan."
        )

    try:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return ArchiveResult(
            ok=False,
            output_path=output_path,
            error=f"Gagal menyiapkan direktori output: {exc}",
        )

    try:
        if fmt == "zip":
            added, skipped = _write_zip(items, output_path)
        else:
            added, skipped = _write_targz(items, output_path)
    except OSError as exc:
        return ArchiveResult(
            ok=False, output_path=output_path, error=f"Gagal menulis arsip: {exc}"
        )
    except Exception as exc:  # pragma: no cover - defensive
        return ArchiveResult(
            ok=False, output_path=output_path, error=f"Kesalahan tak terduga: {exc}"
        )

    if added == 0:
        # Nothing usable was archived.
        try:
            os.remove(output_path)
        except OSError:
            pass
        return ArchiveResult(
            ok=False,
            output_path=output_path,
            skipped=skipped,
            error="Tidak ada file yang berhasil diarsipkan (semua sumber dilewati).",
        )

    try:
        size = os.path.getsize(output_path)
    except OSError:
        size = 0

    return ArchiveResult(
        ok=True,
        output_path=output_path,
        size_bytes=size,
        files_added=added,
        skipped=skipped,
    )


def _write_zip(items: list[ArchiveItem], output_path: str) -> tuple[int, list[str]]:
    """Write items into a ZIP archive. Returns (files_added, skipped)."""
    added = 0
    skipped: list[str] = []

    with zipfile.ZipFile(
        output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for item in items:
            src = Path(item.path)
            base = _safe_arcname(item)

            if not src.exists():
                skipped.append(f"{item.path} (tidak ditemukan)")
                continue

            if src.is_file():
                try:
                    zf.write(src, arcname=base)
                    added += 1
                except (OSError, PermissionError) as exc:
                    skipped.append(f"{item.path} ({exc})")
                continue

            # Directory: walk recursively.
            for root, _dirs, files in os.walk(src):
                for fname in files:
                    fpath = Path(root) / fname
                    try:
                        rel = fpath.relative_to(src)
                        arc = str(Path(base) / rel)
                        zf.write(fpath, arcname=arc)
                        added += 1
                    except (OSError, PermissionError, ValueError) as exc:
                        skipped.append(f"{fpath} ({exc})")

    return added, skipped


def _write_targz(items: list[ArchiveItem], output_path: str) -> tuple[int, list[str]]:
    """Write items into a tar.gz archive. Returns (files_added, skipped)."""
    added = 0
    skipped: list[str] = []

    with tarfile.open(output_path, "w:gz", compresslevel=6) as tf:
        for item in items:
            src = Path(item.path)
            base = _safe_arcname(item)

            if not src.exists():
                skipped.append(f"{item.path} (tidak ditemukan)")
                continue

            if src.is_file():
                try:
                    tf.add(src, arcname=base, recursive=False)
                    added += 1
                except (OSError, PermissionError) as exc:
                    skipped.append(f"{item.path} ({exc})")
                continue

            for root, _dirs, files in os.walk(src):
                for fname in files:
                    fpath = Path(root) / fname
                    try:
                        rel = fpath.relative_to(src)
                        arc = str(Path(base) / rel)
                        tf.add(fpath, arcname=arc, recursive=False)
                        added += 1
                    except (OSError, PermissionError, ValueError) as exc:
                        skipped.append(f"{fpath} ({exc})")

    return added, skipped


def human_size(num: float) -> str:
    """Return a human-friendly byte size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}".strip()
        num /= 1024.0
    return f"{num:.1f} PB"
