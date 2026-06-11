"""Google Drive destination adapter using OAuth (per-account refresh token).

Each Google Drive destination represents one Google account the user has
connected via the OAuth consent flow (see app/services/gdrive_oauth.py).
Backups are uploaded to *that user's* Drive.

Config (stored on the Destination):
    refresh_token (str): OAuth refresh token (stored ENCRYPTED in DB).
    email (str): connected account email (display only).
    folder_id (str): optional Drive folder ID to upload into.

Scope is drive.file, so listing/restore only sees files this app created.
"""

from __future__ import annotations

import io
import os

from app.config import settings
from app.services import crypto
from app.services.destinations.base import (
    ArchiveEntry,
    DestinationAdapter,
    DownloadResult,
    ListResult,
    TestResult,
    UploadResult,
)

_ARCHIVE_EXT = (".zip", ".tar.gz", ".tgz")


def _is_archive(name: str) -> bool:
    n = (name or "").lower()
    return n.endswith(_ARCHIVE_EXT)


class GDriveAdapter(DestinationAdapter):
    type_key = "gdrive"
    label = "Google Drive"

    def _refresh_token(self) -> str:
        """Return the decrypted refresh token (may raise CryptoNotConfigured)."""
        raw = (self.config.get("refresh_token") or "").strip()
        if not raw:
            return ""
        return crypto.decrypt(raw)

    def _service(self):
        """Build an authenticated Drive v3 service from the refresh token.

        Raises:
            ImportError: SDK missing.
            ValueError: not configured / no token.
        """
        if not settings.google_oauth_ready:
            raise ValueError(
                "Google OAuth belum dikonfigurasi di server (.env)."
            )

        refresh_token = self._refresh_token()
        if not refresh_token:
            raise ValueError("Akun Google Drive belum terhubung.")

        from google.oauth2.credentials import Credentials  # lazy import
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _folder_id(self) -> str:
        return (self.config.get("folder_id") or "").strip()

    def ensure_folder(self, folder_name: str) -> str | None:
        """Create a Drive folder by name and return its id (or None on error).

        Used to auto-provision a destination folder when the user leaves
        Folder ID empty.
        """
        try:
            service = self._service()
        except Exception:  # pragma: no cover - defensive
            return None
        return _create_folder(service, folder_name)

    # -- Upload -------------------------------------------------------------
    def upload(self, local_path: str, remote_name: str, subfolder: str = "") -> UploadResult:
        # Drive organizes per connected account via folder_id; `subfolder`
        # is accepted for interface parity but not used here.
        try:
            service = self._service()
        except ImportError:
            return UploadResult(
                ok=False,
                error="Library Google API belum terpasang (google-api-python-client).",
            )
        except crypto.CryptoNotConfigured as exc:
            return UploadResult(ok=False, error=str(exc))
        except ValueError as exc:
            return UploadResult(ok=False, error=str(exc))
        except Exception as exc:  # pragma: no cover
            return UploadResult(ok=False, error=f"Inisialisasi Drive gagal: {exc}")

        try:
            from googleapiclient.http import MediaFileUpload

            metadata = {"name": remote_name}
            folder_id = self._folder_id()
            if folder_id:
                metadata["parents"] = [folder_id]

            media = MediaFileUpload(local_path, resumable=True)
            created = (
                service.files()
                .create(body=metadata, media_body=media, fields="id")
                .execute()
            )
        except Exception as exc:
            return UploadResult(ok=False, error=f"Upload Drive gagal: {exc}")

        return UploadResult(ok=True, location=f"gdrive:{created.get('id', remote_name)}")

    # -- Test ---------------------------------------------------------------
    def test_connection(self) -> TestResult:
        try:
            service = self._service()
        except ImportError:
            return self._missing_sdk(
                "google-api-python-client", "pip install google-api-python-client"
            )
        except crypto.CryptoNotConfigured as exc:
            return TestResult(ok=False, message=str(exc))
        except ValueError as exc:
            return TestResult(ok=False, message=str(exc))
        except Exception as exc:  # pragma: no cover
            return TestResult(ok=False, message=f"Inisialisasi Drive gagal: {exc}")

        try:
            service.files().list(pageSize=1, fields="files(id)").execute()
        except Exception as exc:
            return TestResult(ok=False, message=f"Tidak dapat mengakses Drive: {exc}")

        email = self.config.get("email") or ""
        suffix = f" ({email})" if email else ""
        return TestResult(ok=True, message=f"Koneksi Google Drive berhasil{suffix}.")

    # -- List (restore) -----------------------------------------------------
    def list_archives(self) -> ListResult:
        try:
            service = self._service()
        except ImportError:
            return ListResult(ok=False, error="Library Google API belum terpasang.")
        except crypto.CryptoNotConfigured as exc:
            return ListResult(ok=False, error=str(exc))
        except ValueError as exc:
            return ListResult(ok=False, error=str(exc))
        except Exception as exc:  # pragma: no cover
            return ListResult(ok=False, error=f"Inisialisasi Drive gagal: {exc}")

        query_parts = ["trashed=false"]
        folder_id = self._folder_id()
        if folder_id:
            query_parts.append(f"'{folder_id}' in parents")
        query = " and ".join(query_parts)

        entries: list[ArchiveEntry] = []
        try:
            page_token = None
            while True:
                resp = (
                    service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, size, modifiedTime)",
                        pageToken=page_token,
                        pageSize=100,
                    )
                    .execute()
                )
                for f in resp.get("files", []):
                    name = f.get("name", "")
                    if not _is_archive(name):
                        continue
                    modified = (f.get("modifiedTime") or "")[:16].replace("T", " ")
                    entries.append(
                        ArchiveEntry(
                            name=name,
                            size=int(f.get("size", 0) or 0),
                            modified=modified,
                            ref=f.get("id", ""),
                        )
                    )
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except Exception as exc:
            return ListResult(ok=False, error=f"Gagal mendaftar arsip Drive: {exc}")

        entries.sort(key=lambda e: e.modified, reverse=True)
        return ListResult(ok=True, entries=entries)

    # -- Download (restore) -------------------------------------------------
    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        try:
            service = self._service()
        except ImportError:
            return DownloadResult(ok=False, error="Library Google API belum terpasang.")
        except crypto.CryptoNotConfigured as exc:
            return DownloadResult(ok=False, error=str(exc))
        except ValueError as exc:
            return DownloadResult(ok=False, error=str(exc))
        except Exception as exc:  # pragma: no cover
            return DownloadResult(ok=False, error=f"Inisialisasi Drive gagal: {exc}")

        try:
            from googleapiclient.http import MediaIoBaseDownload

            # Resolve the file name.
            meta = service.files().get(fileId=ref, fields="name").execute()
            name = meta.get("name", "download.bin")

            os.makedirs(dest_dir, exist_ok=True)
            out_path = os.path.join(dest_dir, name)

            request = service.files().get_media(fileId=ref)
            with io.FileIO(out_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _status, done = downloader.next_chunk()
        except Exception as exc:
            return DownloadResult(ok=False, error=f"Gagal mengunduh dari Drive: {exc}")

        return DownloadResult(ok=True, local_path=out_path)


# --- Module-level helpers (used by the OAuth callback) ----------------------


def _build_service_from_token(refresh_token: str):
    """Build a Drive v3 service from a (plaintext) refresh token."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _create_folder(service, folder_name: str) -> str | None:
    """Create a Drive folder and return its id (or None on failure)."""
    name = (folder_name or "").strip() or "Quenza Backups"
    try:
        meta = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        created = service.files().create(body=meta, fields="id").execute()
        return created.get("id")
    except Exception:  # pragma: no cover - network/auth errors
        return None


def create_folder_with_token(refresh_token: str, folder_name: str) -> str | None:
    """Create a Drive folder using a refresh token; return folder id or None.

    Returns None if the SDK is missing, OAuth is not configured, or the API
    call fails — callers should treat None as "skip auto-folder".
    """
    if not refresh_token or not settings.google_oauth_ready:
        return None
    try:
        service = _build_service_from_token(refresh_token)
    except Exception:  # pragma: no cover
        return None
    return _create_folder(service, folder_name)
