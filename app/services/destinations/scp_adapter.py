"""SCP/SFTP destination adapter using paramiko (transfer over SSH).

Supports password and private-key authentication. Secrets (password,
private key, passphrase) are stored ENCRYPTED at rest.

Config:
    host (str), port (int, default 22)
    user (str)
    auth_method (str): "password" | "key"
    password (str, ENCRYPTED) - for password auth
    private_key (str, ENCRYPTED) - PEM contents or path, for key auth
    passphrase (str, ENCRYPTED) - optional key passphrase
    remote_dir (str): base directory on the remote server
"""

from __future__ import annotations

import io
import os
import posixpath

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


class ScpAdapter(DestinationAdapter):
    type_key = "scp"
    label = "SCP / SSH"

    def _decrypt(self, key: str) -> str:
        raw = self.config.get(key) or ""
        if not raw:
            return ""
        return crypto.decrypt(raw)

    def _connect(self):
        """Open an SSH client + SFTP session. Returns (ssh, sftp).

        Raises ValueError on config problems, paramiko errors on connection.
        """
        import paramiko

        host = (self.config.get("host") or "").strip()
        if not host:
            raise ValueError("Host SSH belum diatur.")
        try:
            port = int(self.config.get("port") or 22)
        except (TypeError, ValueError):
            port = 22
        user = (self.config.get("user") or "").strip()
        if not user:
            raise ValueError("Username SSH belum diatur.")

        auth = (self.config.get("auth_method") or "password").strip().lower()

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": host,
            "port": port,
            "username": user,
            "timeout": _TIMEOUT,
            "allow_agent": False,
            "look_for_keys": False,
        }

        if auth == "key":
            key_material = self._decrypt("private_key")
            passphrase = self._decrypt("passphrase") or None
            if not key_material:
                raise ValueError("Private key SSH belum diatur.")
            pkey = _load_private_key(key_material, passphrase)
            if pkey is None:
                raise ValueError("Private key tidak valid atau passphrase salah.")
            connect_kwargs["pkey"] = pkey
        else:
            password = self._decrypt("password")
            if not password:
                raise ValueError("Password SSH belum diatur.")
            connect_kwargs["password"] = password

        ssh.connect(**connect_kwargs)
        sftp = ssh.open_sftp()
        return ssh, sftp

    def _base_dir(self) -> str:
        return (self.config.get("remote_dir") or "").strip().rstrip("/") or "."

    def _ensure_dir(self, sftp, path: str) -> None:
        """Create nested directories on the remote (mkdir -p style)."""
        if not path or path == ".":
            return
        parts = [p for p in path.split("/") if p]
        # Absolute vs relative
        current = "/" if path.startswith("/") else ""
        for part in parts:
            current = posixpath.join(current, part) if current else part
            try:
                sftp.stat(current)
            except IOError:
                try:
                    sftp.mkdir(current)
                except IOError:
                    pass

    def upload(self, local_path: str, remote_name: str, subfolder: str = "") -> UploadResult:
        try:
            ssh, sftp = self._connect()
        except ImportError:
            return UploadResult(ok=False, error="Library 'paramiko' belum terpasang.")
        except ValueError as exc:
            return UploadResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return UploadResult(ok=False, error=str(exc))
        except Exception as exc:
            return UploadResult(ok=False, error=f"Koneksi SSH gagal: {exc}")

        try:
            target_dir = self._base_dir()
            if subfolder:
                target_dir = posixpath.join(target_dir, _safe_segment(subfolder))
            self._ensure_dir(sftp, target_dir)
            remote_path = posixpath.join(target_dir, remote_name)
            sftp.put(local_path, remote_path)
        except (OSError, IOError) as exc:
            return UploadResult(ok=False, error=f"Upload SCP gagal: {exc}")
        finally:
            _close(ssh, sftp)

        return UploadResult(ok=True, location=f"scp://{self.config.get('host')}/{remote_path}")

    def test_connection(self) -> TestResult:
        try:
            ssh, sftp = self._connect()
        except ImportError:
            return self._missing_sdk("paramiko", "pip install paramiko")
        except ValueError as exc:
            return TestResult(ok=False, message=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return TestResult(ok=False, message=str(exc))
        except Exception as exc:
            return TestResult(ok=False, message=f"Koneksi SSH gagal: {exc}")
        try:
            sftp.listdir(".")
        except Exception as exc:
            return TestResult(ok=False, message=f"SFTP error: {exc}")
        finally:
            _close(ssh, sftp)
        return TestResult(ok=True, message="Koneksi SSH/SFTP berhasil.")

    def list_archives(self) -> ListResult:
        try:
            ssh, sftp = self._connect()
        except ImportError:
            return ListResult(ok=False, error="Library 'paramiko' belum terpasang.")
        except ValueError as exc:
            return ListResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return ListResult(ok=False, error=str(exc))
        except Exception as exc:
            return ListResult(ok=False, error=f"Koneksi SSH gagal: {exc}")

        entries: list[ArchiveEntry] = []
        base = self._base_dir()
        try:
            import stat as statmod

            def scan(directory: str, depth: int):
                try:
                    items = sftp.listdir_attr(directory)
                except IOError:
                    return
                for attr in items:
                    name = attr.filename
                    full = posixpath.join(directory, name)
                    if statmod.S_ISDIR(attr.st_mode):
                        if depth > 0:
                            scan(full, depth - 1)
                    elif _is_archive(name):
                        modified = ""
                        if attr.st_mtime:
                            from datetime import datetime, timezone

                            modified = datetime.fromtimestamp(
                                attr.st_mtime, tz=timezone.utc
                            ).strftime("%Y-%m-%d %H:%M")
                        entries.append(
                            ArchiveEntry(
                                name=full,
                                size=int(attr.st_size or 0),
                                modified=modified,
                                ref=full,
                            )
                        )

            # Scan base + one level of subdirectories (per-project layout).
            scan(base, 1)
        except Exception as exc:
            return ListResult(ok=False, error=f"Gagal mendaftar arsip SCP: {exc}")
        finally:
            _close(ssh, sftp)

        entries.sort(key=lambda e: e.modified, reverse=True)
        return ListResult(ok=True, entries=entries)

    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        try:
            ssh, sftp = self._connect()
        except ImportError:
            return DownloadResult(ok=False, error="Library 'paramiko' belum terpasang.")
        except ValueError as exc:
            return DownloadResult(ok=False, error=str(exc))
        except crypto.CryptoNotConfigured as exc:
            return DownloadResult(ok=False, error=str(exc))
        except Exception as exc:
            return DownloadResult(ok=False, error=f"Koneksi SSH gagal: {exc}")

        try:
            os.makedirs(dest_dir, exist_ok=True)
            name = posixpath.basename(ref)
            out_path = os.path.join(dest_dir, name)
            sftp.get(ref, out_path)
        except (OSError, IOError) as exc:
            return DownloadResult(ok=False, error=f"Gagal mengunduh dari SCP: {exc}")
        finally:
            _close(ssh, sftp)

        return DownloadResult(ok=True, local_path=out_path)


def _load_private_key(material: str, passphrase: str | None):
    """Load a private key from PEM text or a file path; try common types."""
    import paramiko

    # Resolve to a readable text blob.
    text = material
    if os.path.isfile(material):
        try:
            with open(material, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return None

    for key_cls in (
        paramiko.Ed25519Key,
        paramiko.RSAKey,
        paramiko.ECDSAKey,
        paramiko.DSSKey,
    ):
        try:
            return key_cls.from_private_key(io.StringIO(text), password=passphrase)
        except Exception:
            continue
    return None


def _close(ssh, sftp) -> None:
    try:
        sftp.close()
    except Exception:  # pragma: no cover
        pass
    try:
        ssh.close()
    except Exception:  # pragma: no cover
        pass
