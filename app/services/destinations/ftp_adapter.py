"""FTP destination adapter using the standard-library ftplib.

Config:
    host (str), port (int, default 21)
    user (str), password (str, ENCRYPTED at rest)
    remote_dir (str): base directory on the FTP server
    passive (bool): passive mode (default True)
"""

from __future__ import annotations

import ftplib
import os
from pathlib import Path

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
_TIMEOUT = 30


def _is_archive(name: str) -> bool:
    n = (name or "").lower()
    return n.endswith(_ARCHIVE_EXT)


def _safe_segment(name: str) -> str:
    keep = "-_."
    cleaned = "".join(c if (c.isalnum() or c in keep) else "_" for c in (name or ""))
    return cleaned.strip("_/ ") or "project"


class FtpAdapter(DestinationAdapter):
    type_key = "ftp"
    label = "FTP"

    def _conn(self) -> ftplib.FTP:
        """Open and login an FTP connection. Raises on error."""
        host = (self.config.get("host") or "").strip()
        if not host:
            raise ValueError("Host FTP belum diatur.")
        try:
            port = int(self.config.get("port") or 21)
        except (TypeError, ValueError):
            port = 21
        user = (self.config.get("user") or "").strip() or "anonymous"
        password = self.config.get("password") or ""
        if password:
            password = crypto.decrypt(password)

        ftp = ftplib.FTP(timeout=_TIMEOUT)
        ftp.connect(host, port)
        ftp.login(user, password)
        passive = self.config.get("passive", True)
        ftp.set_pasv(bool(passive) if passive != "" else True)
        return ftp

    def _base_dir(self) -> str:
        return (self.config.get("remote_dir") or "").strip().strip("/")

    def _ensure_dir(self, ftp: ftplib.FTP, path: str) -> None:
        """Create nested directories on the FTP server (mkdir -p style)."""
        if not path:
            return
        parts = [p for p in path.split("/") if p]
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else part
            try:
                ftp.cwd("/" + current)
            except ftplib.error_perm:
                try:
                    ftp.mkd("/" + current)
                except ftplib.error_perm:
                    pass  # may already exist due to race / permissions

    def upload(self, local_path: str, remote_name: str, subfolder: str = "") -> UploadResult:
        try:
            ftp = self._conn()
        except ValueError as exc:
            return UploadResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return UploadResult(ok=False, error=str(exc))
        except (ftplib.all_errors) as exc:
            return UploadResult(ok=False, error=f"Koneksi FTP gagal: {exc}")

        try:
            target_dir = self._base_dir()
            if subfolder:
                seg = _safe_segment(subfolder)
                target_dir = f"{target_dir}/{seg}" if target_dir else seg
            self._ensure_dir(ftp, target_dir)
            remote_path = f"/{target_dir}/{remote_name}" if target_dir else f"/{remote_name}"
            with open(local_path, "rb") as fh:
                ftp.storbinary(f"STOR {remote_path}", fh)
        except (ftplib.all_errors, OSError) as exc:
            return UploadResult(ok=False, error=f"Upload FTP gagal: {exc}")
        finally:
            try:
                ftp.quit()
            except Exception:  # pragma: no cover
                pass

        return UploadResult(ok=True, location=f"ftp://{self.config.get('host')}{remote_path}")

    def test_connection(self) -> TestResult:
        try:
            ftp = self._conn()
        except ValueError as exc:
            return TestResult(ok=False, message=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return TestResult(ok=False, message=str(exc))
        except ftplib.all_errors as exc:
            return TestResult(ok=False, message=f"Koneksi FTP gagal: {exc}")
        try:
            ftp.voidcmd("NOOP")
        except ftplib.all_errors as exc:
            return TestResult(ok=False, message=f"FTP error: {exc}")
        finally:
            try:
                ftp.quit()
            except Exception:  # pragma: no cover
                pass
        return TestResult(ok=True, message="Koneksi FTP berhasil.")

    def list_archives(self) -> ListResult:
        try:
            ftp = self._conn()
        except ValueError as exc:
            return ListResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return ListResult(ok=False, error=str(exc))
        except ftplib.all_errors as exc:
            return ListResult(ok=False, error=f"Koneksi FTP gagal: {exc}")

        entries: list[ArchiveEntry] = []
        base = self._base_dir()
        try:
            # Walk base dir + one level of subfolders (per-project layout).
            dirs_to_scan = [base]
            try:
                ftp.cwd("/" + base if base else "/")
                for name, facts in _safe_mlsd(ftp):
                    if facts.get("type") == "dir":
                        sub = f"{base}/{name}" if base else name
                        dirs_to_scan.append(sub)
            except ftplib.all_errors:
                pass

            for d in dirs_to_scan:
                try:
                    ftp.cwd("/" + d if d else "/")
                except ftplib.all_errors:
                    continue
                for name, facts in _safe_mlsd(ftp):
                    if facts.get("type") not in (None, "file"):
                        continue
                    if not _is_archive(name):
                        continue
                    size = int(facts.get("size", 0) or 0)
                    modify = facts.get("modify", "")
                    modified = ""
                    if modify and len(modify) >= 12:
                        modified = f"{modify[0:4]}-{modify[4:6]}-{modify[6:8]} {modify[8:10]}:{modify[10:12]}"
                    ref = f"/{d}/{name}" if d else f"/{name}"
                    display = f"{d}/{name}" if d else name
                    entries.append(
                        ArchiveEntry(name=display, size=size, modified=modified, ref=ref)
                    )
        except ftplib.all_errors as exc:
            return ListResult(ok=False, error=f"Gagal mendaftar arsip FTP: {exc}")
        finally:
            try:
                ftp.quit()
            except Exception:  # pragma: no cover
                pass

        entries.sort(key=lambda e: e.modified, reverse=True)
        return ListResult(ok=True, entries=entries)

    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        try:
            ftp = self._conn()
        except ValueError as exc:
            return DownloadResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return DownloadResult(ok=False, error=str(exc))
        except ftplib.all_errors as exc:
            return DownloadResult(ok=False, error=f"Koneksi FTP gagal: {exc}")

        try:
            os.makedirs(dest_dir, exist_ok=True)
            name = Path(ref).name
            out_path = os.path.join(dest_dir, name)
            with open(out_path, "wb") as fh:
                ftp.retrbinary(f"RETR {ref}", fh.write)
        except (ftplib.all_errors, OSError) as exc:
            return DownloadResult(ok=False, error=f"Gagal mengunduh dari FTP: {exc}")
        finally:
            try:
                ftp.quit()
            except Exception:  # pragma: no cover
                pass

        return DownloadResult(ok=True, local_path=out_path)


def _safe_mlsd(ftp: ftplib.FTP):
    """Yield (name, facts) using MLSD, falling back to NLST when unsupported."""
    try:
        yield from ftp.mlsd()
    except (ftplib.error_perm, ftplib.error_proto, AttributeError):
        try:
            for name in ftp.nlst():
                base = name.rsplit("/", 1)[-1]
                yield base, {}
        except ftplib.all_errors:
            return
