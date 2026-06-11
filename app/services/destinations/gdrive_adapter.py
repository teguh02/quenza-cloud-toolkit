"""Google Drive destination adapter using PyDrive2 (lazy import).

Authentication uses a Service Account JSON for unattended/server use,
which is the most reliable method for an internal tool without an
interactive OAuth consent flow.

Config:
    service_account_json (str): raw JSON or path to the key file.
    folder_id (str): optional Drive folder ID to upload into.
"""

from __future__ import annotations

import json
import os
import tempfile

from app.services.destinations.base import (
    DestinationAdapter,
    TestResult,
    UploadResult,
)


class GDriveAdapter(DestinationAdapter):
    type_key = "gdrive"
    label = "Google Drive"

    def _write_keyfile(self) -> str | None:
        """Return a path to the service-account key file.

        Accepts either a filesystem path or raw JSON in the config.
        """
        raw = (self.config.get("service_account_json") or "").strip()
        if not raw:
            return None
        if os.path.isfile(raw):
            return raw
        # Treat as raw JSON: validate and write to a temp file.
        try:
            json.loads(raw)
        except json.JSONDecodeError:
            return None
        fd, path = tempfile.mkstemp(suffix=".json", prefix="quenza_sa_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
        return path

    def _drive(self):
        """Build an authenticated GoogleDrive client (lazy import)."""
        from pydrive2.auth import GoogleAuth  # lazy import
        from pydrive2.drive import GoogleDrive

        keyfile = self._write_keyfile()
        if not keyfile:
            raise ValueError("Service Account JSON tidak valid atau kosong.")

        gauth = GoogleAuth()
        gauth.settings["client_config_backend"] = "service"
        gauth.settings["service_config"] = {
            "client_json_file_path": keyfile,
        }
        gauth.ServiceAuth()
        return GoogleDrive(gauth)

    def upload(self, local_path: str, remote_name: str) -> UploadResult:
        try:
            drive = self._drive()
        except ImportError:
            return UploadResult(
                ok=False,
                error="Library 'PyDrive2' belum terpasang (pip install PyDrive2).",
            )
        except ValueError as exc:
            return UploadResult(ok=False, error=str(exc))
        except Exception as exc:  # pragma: no cover - auth errors
            return UploadResult(ok=False, error=f"Autentikasi Drive gagal: {exc}")

        meta = {"title": remote_name}
        folder_id = (self.config.get("folder_id") or "").strip()
        if folder_id:
            meta["parents"] = [{"id": folder_id}]

        try:
            f = drive.CreateFile(meta)
            f.SetContentFile(local_path)
            f.Upload()
        except Exception as exc:
            return UploadResult(ok=False, error=f"Upload Drive gagal: {exc}")

        return UploadResult(ok=True, location=f"gdrive:{remote_name}")

    def test_connection(self) -> TestResult:
        try:
            drive = self._drive()
        except ImportError:
            return self._missing_sdk("PyDrive2", "pip install PyDrive2")
        except ValueError as exc:
            return TestResult(ok=False, message=str(exc))
        except Exception as exc:  # pragma: no cover
            return TestResult(ok=False, message=f"Autentikasi Drive gagal: {exc}")

        try:
            # A cheap call to confirm the credentials work.
            drive.ListFile({"q": "trashed=false", "maxResults": 1}).GetList()
        except Exception as exc:
            return TestResult(ok=False, message=f"Tidak dapat mengakses Drive: {exc}")

        return TestResult(ok=True, message="Koneksi Google Drive berhasil.")
