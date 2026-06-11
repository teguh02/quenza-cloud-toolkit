"""Mega.nz destination adapter using mega.py (lazy import).

Config:
    email (str): Mega account email.
    password (str): Mega account password.
    folder (str): optional destination folder name in Mega.
"""

from __future__ import annotations

from app.services.destinations.base import (
    DestinationAdapter,
    TestResult,
    UploadResult,
)


class MegaAdapter(DestinationAdapter):
    type_key = "mega"
    label = "Mega.nz"

    def _login(self):
        """Authenticate and return a Mega client (lazy import)."""
        from mega import Mega  # lazy import

        email = (self.config.get("email") or "").strip()
        password = self.config.get("password") or ""
        if not email or not password:
            raise ValueError("Email dan password Mega wajib diisi.")

        mega = Mega()
        return mega.login(email, password)

    def upload(self, local_path: str, remote_name: str) -> UploadResult:
        try:
            m = self._login()
        except ImportError:
            return UploadResult(
                ok=False,
                error="Library 'mega.py' belum terpasang (pip install mega.py).",
            )
        except ValueError as exc:
            return UploadResult(ok=False, error=str(exc))
        except Exception as exc:  # pragma: no cover - auth errors
            return UploadResult(ok=False, error=f"Login Mega gagal: {exc}")

        folder_name = (self.config.get("folder") or "").strip()
        try:
            dest_folder = None
            if folder_name:
                found = m.find(folder_name)
                if found:
                    dest_folder = found[0]
                else:
                    dest_folder = m.create_folder(folder_name)
                    # create_folder returns a dict {name: handle}
                    if isinstance(dest_folder, dict):
                        dest_folder = list(dest_folder.values())[0]
            if dest_folder is not None:
                m.upload(local_path, dest_folder, dest_filename=remote_name)
            else:
                m.upload(local_path, dest_filename=remote_name)
        except Exception as exc:
            return UploadResult(ok=False, error=f"Upload Mega gagal: {exc}")

        return UploadResult(ok=True, location=f"mega:{remote_name}")

    def test_connection(self) -> TestResult:
        try:
            self._login()
        except ImportError:
            return self._missing_sdk("mega.py", "pip install mega.py")
        except ValueError as exc:
            return TestResult(ok=False, message=str(exc))
        except Exception as exc:  # pragma: no cover
            return TestResult(ok=False, message=f"Login Mega gagal: {exc}")

        return TestResult(ok=True, message="Login Mega.nz berhasil.")
