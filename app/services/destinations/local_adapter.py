"""Local filesystem destination adapter."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.services.destinations.base import (
    ArchiveEntry,
    DestinationAdapter,
    DownloadResult,
    ListResult,
    TestResult,
    UploadResult,
)


def _is_archive(name: str) -> bool:
    n = name.lower()
    return n.endswith(".zip") or n.endswith(".tar.gz") or n.endswith(".tgz")


def _safe_segment(name: str) -> str:
    """Sanitize a string into a safe single path segment."""
    keep = "-_."
    cleaned = "".join(c if (c.isalnum() or c in keep) else "_" for c in (name or ""))
    return cleaned.strip("_/ ") or "project"


class LocalAdapter(DestinationAdapter):
    """Copy the archive to a local directory.

    Config:
        path (str): target directory on the server.
    """

    type_key = "local"
    label = "Local"

    def _target_dir(self) -> str:
        return (self.config.get("path") or "").strip()

    def upload(self, local_path: str, remote_name: str, subfolder: str = "") -> UploadResult:
        target_dir = self._target_dir()
        if not target_dir:
            return UploadResult(ok=False, error="Path tujuan lokal belum diatur.")

        try:
            dest_dir = Path(target_dir)
            if subfolder:
                dest_dir = dest_dir / _safe_segment(subfolder)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / remote_name
            shutil.copy2(local_path, dest_path)
        except (OSError, PermissionError) as exc:
            return UploadResult(ok=False, error=f"Gagal menyalin ke lokal: {exc}")

        return UploadResult(ok=True, location=str(dest_path))

    def test_connection(self) -> TestResult:
        target_dir = self._target_dir()
        if not target_dir:
            return TestResult(ok=False, message="Path tujuan lokal belum diatur.")
        try:
            d = Path(target_dir)
            d.mkdir(parents=True, exist_ok=True)
            # Probe writability.
            probe = d / ".quenza_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except (OSError, PermissionError) as exc:
            return TestResult(ok=False, message=f"Direktori tidak dapat ditulis: {exc}")
        return TestResult(ok=True, message="Direktori lokal siap digunakan.")

    def list_archives(self) -> ListResult:
        target_dir = self._target_dir()
        if not target_dir:
            return ListResult(ok=False, error="Path tujuan lokal belum diatur.")
        try:
            d = Path(target_dir)
            if not d.is_dir():
                return ListResult(ok=False, error="Direktori tidak ditemukan.")
            entries: list[ArchiveEntry] = []
            # Scan recursively so per-project subfolders are included.
            for child in d.rglob("*"):
                if child.is_file() and _is_archive(child.name):
                    try:
                        stat = child.stat()
                        modified = datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M")
                        size = stat.st_size
                    except OSError:
                        modified, size = "", 0
                    # Show a name relative to the destination root for clarity.
                    try:
                        display = str(child.relative_to(d))
                    except ValueError:
                        display = child.name
                    entries.append(
                        ArchiveEntry(
                            name=display,
                            size=size,
                            modified=modified,
                            ref=str(child),
                        )
                    )
            entries.sort(key=lambda e: e.modified, reverse=True)
            return ListResult(ok=True, entries=entries)
        except (OSError, PermissionError) as exc:
            return ListResult(ok=False, error=f"Gagal membaca direktori: {exc}")

    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        try:
            src = Path(ref)
            if not src.is_file():
                return DownloadResult(ok=False, error="Arsip tidak ditemukan.")
            out_dir = Path(dest_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / src.name
            shutil.copy2(src, out_path)
        except (OSError, PermissionError) as exc:
            return DownloadResult(ok=False, error=f"Gagal mengunduh: {exc}")
        return DownloadResult(ok=True, local_path=str(out_path))
