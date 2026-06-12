#!/usr/bin/env python3
"""Quenza Cloud Toolkit - Management Console.

An interactive (and scriptable) console to manage a Quenza installation:
regenerate the Master Password / keys, manage the service (start/stop/
restart/status/logs), inspect configuration, and run a manual backup.

Usage:
    python toolkit.py                 # interactive menu
    python toolkit.py <command>       # non-interactive

Commands:
    regen-password         Generate a new random Master Password (and show it)
    set-password           Set the Master Password manually (hidden prompt)
    regen-secret           Regenerate SECRET_KEY
    regen-encryption       Regenerate ENCRYPTION_KEY (DANGEROUS)
    set-public-url <url>   Set Public URL / GOOGLE_REDIRECT_URI
    status                 Show service status
    start | stop | restart Manage the service
    logs                   Tail service logs
    config                 Show a non-sensitive configuration summary
    backup [project_id]    Run a manual backup
    check-update           Check whether a newer version is available
    update [--yes]         Update from GitHub, reinstall deps, restart service
    help                   Show this help

Run inside the project's virtual environment so dependencies are available,
e.g.:  ./.venv/bin/python toolkit.py
"""

from __future__ import annotations

import getpass
import io
import os
import secrets
import subprocess
import sys

# Ensure UTF-8 output where possible (Windows consoles may default to cp1252).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 - older Pythons / non-reconfigurable streams
    pass

# Project root = directory of this file.
ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, ".env")
SERVICE_NAME = "quenza"

# Repository / update sources.
REPO_URL = "https://github.com/teguh02/quenza-cloud-toolkit.git"
REPO_BRANCH = "main"
REPO_ZIP = f"https://github.com/teguh02/quenza-cloud-toolkit/archive/refs/heads/{REPO_BRANCH}.zip"
GITHUB_API_COMMIT = f"https://api.github.com/repos/teguh02/quenza-cloud-toolkit/commits/{REPO_BRANCH}"
# Local marker storing the last known commit SHA (for non-git installs).
VERSION_FILE = os.path.join(ROOT, ".quenza_version")

# When updating a non-git install, only these top-level paths are refreshed;
# everything else (.env, .venv, *.db, backups/, logs, secrets) is preserved.
_UPDATE_INCLUDE_DIRS = ("app", "templates", "static", "docs")
_UPDATE_INCLUDE_FILES = (
    "requirements.txt", "install.sh", "install.ps1", "toolkit.py",
    "generate_hash.py", "generate_key.py", "README.md", "CHANGELOG.md",
    ".env.example", ".gitignore",
)

# Ensure the project package is importable (for backup, settings, etc.).
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty()


def _c(code: str) -> str:
    return code if _USE_COLOR else ""


CY = _c("\033[36m"); GR = _c("\033[32m"); YE = _c("\033[33m")
RD = _c("\033[31m"); DIM = _c("\033[2m"); BD = _c("\033[1m"); RS = _c("\033[0m")

# Use unicode marks only if the output encoding can represent them.
def _supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


_OK = "\u2713" if _supports_unicode() else "[OK]"
_BUL = "\u2022" if _supports_unicode() else "*"
_WARN = "!" 
_ERR = "\u2717" if _supports_unicode() else "x"


def info(msg: str) -> None:
    print(f"{CY}{_BUL}{RS} {msg}")


def ok(msg: str) -> None:
    print(f"{GR}{_OK}{RS} {msg}")


def warn(msg: str) -> None:
    print(f"{YE}{_WARN}{RS} {msg}")


def err(msg: str) -> None:
    print(f"{RD}{_ERR}{RS} {msg}")


def banner() -> None:
    print(f"{BD}{CY}")
    print("  Quenza Cloud Toolkit - Management Console")
    print(f"{RS}{DIM}  {ROOT}{RS}\n")


# ---------------------------------------------------------------------------
# .env helpers (safe line-replace, preserve comments)
# ---------------------------------------------------------------------------
def _require_env() -> None:
    if not os.path.isfile(ENV_PATH):
        err(f".env tidak ditemukan di {ENV_PATH}")
        err("Jalankan toolkit.py dari direktori instalasi Quenza.")
        sys.exit(1)


def read_env() -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        # utf-8-sig transparently strips a leading BOM if present.
        with io.open(ENV_PATH, "r", encoding="utf-8-sig") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, _, v = s.partition("=")
                data[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return data


def set_env_var(key: str, value: str) -> None:
    """Replace an existing KEY= line, or append it. Preserves other lines."""
    try:
        with io.open(ENV_PATH, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []
    out, found = [], False
    for ln in lines:
        if ln.lstrip().startswith(key + "="):
            out.append(f"{key}={value}\n")
            found = True
        else:
            out.append(ln)
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key}={value}\n")
    with io.open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(out)


def _python_exe() -> str:
    """Return the interpreter to use (prefer the project venv)."""
    venv = os.path.join(ROOT, ".venv", "bin", "python")
    if os.name == "nt":
        venv = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    return venv if os.path.isfile(venv) else sys.executable


# ---------------------------------------------------------------------------
# Master Password / keys
# ---------------------------------------------------------------------------
def _bcrypt_hash(password: str) -> str:
    try:
        import bcrypt
    except ImportError:
        err("Library 'bcrypt' tidak tersedia. Jalankan toolkit.py via .venv.")
        sys.exit(1)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def regen_password(interactive: bool = True) -> None:
    _require_env()
    password = secrets.token_urlsafe(18)
    set_env_var("MASTER_PASSWORD_HASH", _bcrypt_hash(password))
    ok("Master Password baru dibuat.")
    print()
    print(f"  {YE}{BD}Master Password baru (SIMPAN - hanya tampil sekali):{RS}")
    print(f"  {BD}{password}{RS}")
    print()
    if interactive:
        _maybe_restart_prompt()


def set_password(interactive: bool = True) -> None:
    _require_env()
    p1 = getpass.getpass("Master Password baru: ")
    if not p1:
        err("Password kosong - dibatalkan.")
        return
    p2 = getpass.getpass("Konfirmasi: ")
    if p1 != p2:
        err("Password tidak cocok - dibatalkan.")
        return
    set_env_var("MASTER_PASSWORD_HASH", _bcrypt_hash(p1))
    ok("Master Password diperbarui.")
    if interactive:
        _maybe_restart_prompt()


def regen_secret(interactive: bool = True) -> None:
    _require_env()
    set_env_var("SECRET_KEY", secrets.token_urlsafe(48))
    ok("SECRET_KEY baru dibuat. (Semua sesi login saat ini akan logout.)")
    if interactive:
        _maybe_restart_prompt()


def regen_encryption(interactive: bool = True) -> None:
    _require_env()
    warn("PERINGATAN: Mengganti ENCRYPTION_KEY membuat SEMUA kredensial destinasi")
    warn("yang sudah tersimpan (token Google Drive, password FTP/SCP/S3) TIDAK")
    warn("bisa didekripsi lagi. Anda harus mengonfigurasi ulang destinasi tersebut.")
    if interactive:
        confirm = input('Ketik "HAPUS" untuk melanjutkan: ').strip()
        if confirm != "HAPUS":
            info("Dibatalkan.")
            return
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        err("Library 'cryptography' tidak tersedia. Jalankan toolkit.py via .venv.")
        return
    set_env_var("ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    ok("ENCRYPTION_KEY baru dibuat.")
    if interactive:
        _maybe_restart_prompt()


def set_public_url(url: str | None = None, interactive: bool = True) -> None:
    _require_env()
    if not url:
        url = input("Public URL (mis. https://toolkit.domain.com), kosong untuk lokal: ").strip()
    url = (url or "").rstrip("/")
    env = read_env()
    port = _port_from_env(env)
    if url:
        redirect = f"{url}/destinations/gdrive/callback"
    else:
        redirect = f"http://127.0.0.1:{port}/destinations/gdrive/callback"
    set_env_var("GOOGLE_REDIRECT_URI", redirect)
    ok(f"GOOGLE_REDIRECT_URI = {redirect}")
    warn("Pastikan redirect URI ini terdaftar di Google Cloud Console.")
    if interactive:
        _maybe_restart_prompt()


def _port_from_env(env: dict[str, str]) -> str:
    # Try to infer the port from GOOGLE_REDIRECT_URI; default 8000.
    uri = env.get("GOOGLE_REDIRECT_URI", "")
    if "127.0.0.1:" in uri or "localhost:" in uri:
        try:
            after = uri.split(":")[2]
            return after.split("/")[0]
        except (IndexError, ValueError):
            pass
    return "8000"


# ---------------------------------------------------------------------------
# Service management (Linux systemd + manual fallback; Windows best-effort)
# ---------------------------------------------------------------------------
def _has_systemd_unit() -> bool:
    if os.name == "nt":
        return False
    try:
        r = subprocess.run(
            ["systemctl", "cat", SERVICE_NAME],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return r.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _sudo_prefix() -> list[str]:
    if os.name == "nt":
        return []
    if os.geteuid() == 0:  # type: ignore[attr-defined]
        return []
    # Use sudo only if available.
    try:
        subprocess.run(["sudo", "-n", "true"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    except (FileNotFoundError, OSError):
        return []
    return ["sudo"]


def _systemctl(action: str) -> int:
    cmd = _sudo_prefix() + ["systemctl", action, SERVICE_NAME]
    info("Menjalankan: " + " ".join(cmd))
    try:
        return subprocess.run(cmd).returncode
    except (FileNotFoundError, OSError) as exc:
        err(f"Gagal menjalankan systemctl: {exc}")
        return 1


def _windows_service_action(action: str) -> int:
    # Best-effort: try NSSM in install dir, then sc.
    nssm = os.path.join(ROOT, "nssm", "nssm.exe")
    try:
        if os.path.isfile(nssm):
            return subprocess.run([nssm, action, "Quenza"]).returncode
        mapping = {"start": "start", "stop": "stop", "restart": "stop"}
        sc_act = mapping.get(action, action)
        rc = subprocess.run(["sc", sc_act, "Quenza"]).returncode
        if action == "restart":
            subprocess.run(["sc", "start", "Quenza"])
        return rc
    except (FileNotFoundError, OSError) as exc:
        err(f"Gagal mengelola layanan Windows: {exc}")
        return 1


def _manual_find_pids() -> list[int]:
    """Find uvicorn PIDs serving this install (best-effort, Linux/macOS)."""
    pids: list[int] = []
    try:
        out = subprocess.run(
            ["pgrep", "-f", "uvicorn app.main:app"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        ).stdout
        pids = [int(x) for x in out.split() if x.strip().isdigit()]
    except (FileNotFoundError, OSError, ValueError):
        pass
    return pids


def _manual_start() -> int:
    py = _python_exe()
    env = read_env()
    port = _port_from_env(env)
    log = os.path.join(ROOT, "server.log")
    cmd = [py, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0",
           "--port", str(port), "--proxy-headers", "--forwarded-allow-ips=*"]
    info("Menjalankan manual (nohup): " + " ".join(cmd))
    try:
        with open(log, "ab") as fh:
            subprocess.Popen(cmd, cwd=ROOT, stdout=fh, stderr=fh,
                             start_new_session=True)
        ok(f"Layanan dijalankan. Log: {log}")
        return 0
    except (FileNotFoundError, OSError) as exc:
        err(f"Gagal menjalankan: {exc}")
        return 1


def service_status() -> None:
    if _has_systemd_unit():
        _systemctl("status")
    elif os.name == "nt":
        _windows_service_action("query")
    else:
        pids = _manual_find_pids()
        if pids:
            ok(f"Berjalan (manual), PID: {', '.join(map(str, pids))}")
        else:
            warn("Layanan tidak terdeteksi berjalan (mode manual).")


def service_start() -> None:
    if _has_systemd_unit():
        _systemctl("start")
    elif os.name == "nt":
        _windows_service_action("start")
    else:
        _manual_start()


def service_stop() -> None:
    if _has_systemd_unit():
        _systemctl("stop")
    elif os.name == "nt":
        _windows_service_action("stop")
    else:
        pids = _manual_find_pids()
        if not pids:
            warn("Tidak ada proses untuk dihentikan.")
            return
        for pid in pids:
            try:
                os.kill(pid, 15)
            except OSError:
                pass
        ok(f"Menghentikan PID: {', '.join(map(str, pids))}")


def service_restart() -> None:
    if _has_systemd_unit():
        _systemctl("restart")
    elif os.name == "nt":
        _windows_service_action("restart")
    else:
        service_stop()
        import time
        time.sleep(1)
        _manual_start()


def service_logs() -> None:
    if _has_systemd_unit():
        cmd = _sudo_prefix() + ["journalctl", "-u", SERVICE_NAME, "-n", "100", "-f"]
        info("Ctrl+C untuk keluar.")
        try:
            subprocess.run(cmd)
        except KeyboardInterrupt:
            pass
        except (FileNotFoundError, OSError) as exc:
            err(f"Gagal membaca log: {exc}")
    else:
        log = os.path.join(ROOT, "server.log")
        if not os.path.isfile(log):
            warn(f"Log tidak ditemukan: {log}")
            return
        info(f"Menampilkan 100 baris terakhir: {log} (Ctrl+C keluar)")
        try:
            subprocess.run(["tail", "-n", "100", "-f", log])
        except KeyboardInterrupt:
            pass
        except (FileNotFoundError, OSError):
            # Windows fallback: print last lines.
            with io.open(log, "r", encoding="utf-8", errors="replace") as f:
                for line in f.readlines()[-100:]:
                    print(line, end="")


def _maybe_restart_prompt() -> None:
    ans = input("Restart layanan sekarang agar perubahan berlaku? [y/N] ").strip().lower()
    if ans in ("y", "yes"):
        service_restart()


# ---------------------------------------------------------------------------
# Config summary (non-sensitive)
# ---------------------------------------------------------------------------
_SENSITIVE = ("MASTER_PASSWORD_HASH", "SECRET_KEY", "ENCRYPTION_KEY",
              "GOOGLE_CLIENT_SECRET")


def show_config() -> None:
    _require_env()
    env = read_env()
    print(f"{BD}Ringkasan konfigurasi (.env):{RS}")
    for key in sorted(env):
        val = env[key]
        if key in _SENSITIVE:
            shown = "(terisi)" if val else "(kosong)"
        elif key == "GOOGLE_CLIENT_ID":
            shown = (val[:10] + "...") if val else "(kosong)"
        else:
            shown = val if val else "(kosong)"
        print(f"  {key:24s}: {shown}")
    print()
    print(f"  {DIM}Service systemd unit : {_has_systemd_unit()}{RS}")


# ---------------------------------------------------------------------------
# Manual backup
# ---------------------------------------------------------------------------
def run_backup(project_id: int | None = None, interactive: bool = True) -> None:
    _require_env()
    try:
        from app.database import SessionLocal
        from app.models import Project
        from app.services import backup_service
    except Exception as exc:  # noqa: BLE001
        err(f"Gagal memuat modul aplikasi: {exc}")
        err("Pastikan dijalankan via .venv: ./.venv/bin/python toolkit.py")
        return

    db = SessionLocal()
    try:
        projects = db.query(Project).order_by(Project.id).all()
        if not projects:
            warn("Belum ada project. Buat project lewat antarmuka web dulu.")
            return

        if project_id is None and interactive:
            print(f"{BD}Daftar project:{RS}")
            for p in projects:
                print(f"  [{p.id}] {p.name}")
            raw = input("Masukkan ID project untuk di-backup: ").strip()
            if not raw.isdigit():
                err("ID tidak valid.")
                return
            project_id = int(raw)

        if project_id is None:
            err("Project ID diperlukan.")
            return

        if not any(p.id == project_id for p in projects):
            err(f"Project id {project_id} tidak ditemukan.")
            return
    finally:
        db.close()

    info(f"Menjalankan backup project id {project_id}...")
    result = backup_service.run_backup(project_id, trigger="manual")
    status = result.get("status")
    msg = result.get("message", "")
    if status == "success":
        ok(f"Backup berhasil: {msg}")
    elif status == "partial":
        warn(f"Backup sebagian: {msg}")
    else:
        err(f"Backup gagal: {msg}")


# ---------------------------------------------------------------------------
# Update / version check
# ---------------------------------------------------------------------------
def _is_git_repo() -> bool:
    if not os.path.isdir(os.path.join(ROOT, ".git")):
        return False
    try:
        r = subprocess.run(
            ["git", "-C", ROOT, "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return r.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _git(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", ROOT, *args],
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True,
    )


def _local_commit() -> str:
    try:
        r = _git("rev-parse", "HEAD")
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, OSError):
        pass
    # Non-git: read stored marker.
    try:
        with io.open(VERSION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _remote_commit_git() -> str:
    r = _git("fetch", "--quiet", "origin", REPO_BRANCH)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "git fetch gagal.")
    rev = _git("rev-parse", f"origin/{REPO_BRANCH}")
    if rev.returncode != 0:
        raise RuntimeError(rev.stderr.strip() or "git rev-parse gagal.")
    return rev.stdout.strip()


def _remote_commit_api() -> str:
    """Fetch the latest commit SHA via the GitHub API (no token)."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "quenza-toolkit"}
    # Prefer httpx (already a dependency); fall back to urllib.
    try:
        import httpx

        resp = httpx.get(GITHUB_API_COMMIT, headers=headers, timeout=20)
        if resp.status_code == 403:
            raise RuntimeError("GitHub API rate limit. Coba lagi nanti atau pakai git.")
        resp.raise_for_status()
        return resp.json().get("sha", "")
    except ImportError:
        pass
    import json as _json
    import urllib.request

    req = urllib.request.Request(GITHUB_API_COMMIT, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            data = _json.loads(r.read().decode("utf-8"))
            return data.get("sha", "")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Gagal menghubungi GitHub API: {exc}") from exc


def _short(sha: str) -> str:
    return sha[:8] if sha else "(tidak diketahui)"


def check_update(verbose: bool = True) -> dict:
    """Return update status: {available, local, remote, commits, method, error}."""
    result = {"available": False, "local": "", "remote": "",
              "commits": [], "method": "", "error": None}
    if _is_git_repo():
        result["method"] = "git"
        result["local"] = _local_commit()
        try:
            result["remote"] = _remote_commit_git()
        except RuntimeError as exc:
            result["error"] = str(exc)
            if verbose:
                err(str(exc))
            return result
        result["available"] = bool(result["remote"]) and result["remote"] != result["local"]
        if result["available"]:
            log = _git("log", "--oneline", f"HEAD..origin/{REPO_BRANCH}")
            if log.returncode == 0 and log.stdout.strip():
                result["commits"] = log.stdout.strip().splitlines()
    else:
        result["method"] = "api"
        result["local"] = _local_commit()  # may be empty
        try:
            result["remote"] = _remote_commit_api()
        except RuntimeError as exc:
            result["error"] = str(exc)
            if verbose:
                err(str(exc))
            return result
        # Without a local marker we cannot be sure; treat as update available.
        result["available"] = (not result["local"]) or (result["remote"] != result["local"])

    if verbose:
        info(f"Versi lokal : {_short(result['local'])}")
        info(f"Versi remote: {_short(result['remote'])}  (via {result['method']})")
        if result["available"]:
            warn("Pembaruan tersedia.")
            if result["commits"]:
                print(f"{DIM}  Perubahan:{RS}")
                for line in result["commits"][:15]:
                    print(f"{DIM}    {line}{RS}")
        else:
            ok("Sudah versi terbaru.")
    return result


def _write_version_marker(sha: str) -> None:
    if not sha:
        return
    try:
        with io.open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(sha + "\n")
    except OSError:
        pass


def _update_via_git() -> bool:
    info("Memperbarui via git (git reset --hard origin/" + REPO_BRANCH + ")...")
    f = _git("fetch", "origin", REPO_BRANCH, capture=False)
    if f.returncode != 0:
        err("git fetch gagal.")
        return False
    r = _git("reset", "--hard", f"origin/{REPO_BRANCH}", capture=False)
    if r.returncode != 0:
        err("git reset --hard gagal.")
        return False
    ok("Kode diperbarui ke versi terbaru.")
    return True


def _update_via_zip() -> bool:
    import shutil
    import tempfile
    import zipfile

    info("Memperbarui via unduh arsip (instalasi non-git)...")
    tmp = tempfile.mkdtemp(prefix="quenza_update_")
    try:
        zip_path = os.path.join(tmp, "src.zip")
        # Download.
        try:
            import httpx

            with httpx.stream("GET", REPO_ZIP, follow_redirects=True, timeout=60) as resp:
                resp.raise_for_status()
                with open(zip_path, "wb") as fh:
                    for chunk in resp.iter_bytes():
                        fh.write(chunk)
        except ImportError:
            import urllib.request

            urllib.request.urlretrieve(REPO_ZIP, zip_path)  # noqa: S310

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        # Find extracted root (quenza-cloud-toolkit-main/).
        srcroot = None
        for name in os.listdir(tmp):
            full = os.path.join(tmp, name)
            if os.path.isdir(full) and name.startswith("quenza-cloud-toolkit-"):
                srcroot = full
                break
        if not srcroot:
            err("Struktur arsip tidak dikenali.")
            return False

        # Copy only whitelisted code paths; never touch data/secret files.
        for d in _UPDATE_INCLUDE_DIRS:
            s = os.path.join(srcroot, d)
            if os.path.isdir(s):
                dest = os.path.join(ROOT, d)
                shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(s, dest)
        for fname in _UPDATE_INCLUDE_FILES:
            s = os.path.join(srcroot, fname)
            if os.path.isfile(s):
                shutil.copy2(s, os.path.join(ROOT, fname))
        ok("Kode diperbarui dari arsip terbaru.")
        return True
    except Exception as exc:  # noqa: BLE001
        err(f"Update via arsip gagal: {exc}")
        return False
    finally:
        import shutil as _sh
        _sh.rmtree(tmp, ignore_errors=True)


def _update_yara_rules() -> None:
    rules_dir = os.path.join(ROOT, "app", "data", "yara_rules")
    if os.path.isdir(os.path.join(rules_dir, ".git")):
        info("Memperbarui basis data YARA (git pull)...")
        r = subprocess.run(["git", "-C", rules_dir, "pull", "--ff-only"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode == 0:
            ok("Basis data YARA diperbarui.")
        else:
            warn("Gagal memperbarui basis data YARA via git.")
    else:
        import tempfile
        import zipfile
        import shutil
        info("Mengunduh basis data YARA terbaru (signature-base)...")
        tmp = tempfile.mkdtemp(prefix="quenza_yara_")
        try:
            zip_path = os.path.join(tmp, "master.zip")
            url = "https://github.com/Neo23x0/signature-base/archive/refs/heads/master.zip"
            try:
                import httpx
                with httpx.stream("GET", url, follow_redirects=True, timeout=60) as resp:
                    resp.raise_for_status()
                    with open(zip_path, "wb") as fh:
                        for chunk in resp.iter_bytes():
                            fh.write(chunk)
            except ImportError:
                import urllib.request
                urllib.request.urlretrieve(url, zip_path)  # noqa: S310

            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            
            os.makedirs(rules_dir, exist_ok=True)
            extracted_dir = os.path.join(tmp, "signature-base-master")
            if os.path.isdir(extracted_dir):
                for name in os.listdir(extracted_dir):
                    s = os.path.join(extracted_dir, name)
                    d = os.path.join(rules_dir, name)
                    if os.path.isdir(s):
                        shutil.rmtree(d, ignore_errors=True)
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)
                ok("Basis data YARA berhasil diunduh dan diperbarui.")
            else:
                warn("Struktur arsip YARA tidak sesuai.")
        except Exception as exc:
            warn(f"Gagal memperbarui basis data YARA: {exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _pip_install_requirements() -> bool:
    req = os.path.join(ROOT, "requirements.txt")
    if not os.path.isfile(req):
        return True
    info("Memasang/memperbarui dependencies (pip install -r requirements.txt)...")
    py = _python_exe()
    try:
        rc = subprocess.run([py, "-m", "pip", "install", "-r", req], cwd=ROOT).returncode
    except (FileNotFoundError, OSError) as exc:
        err(f"Gagal menjalankan pip: {exc}")
        return False
    if rc != 0:
        err("pip install mengembalikan error.")
        return False
    ok("Dependencies terpasang/terbaru.")
    return True


def do_update(assume_yes: bool = False, interactive: bool = True) -> None:
    status = check_update(verbose=True)
    if status.get("error"):
        return
    if not status["available"]:
        info("Tidak ada yang perlu diperbarui.")
        return

    if not assume_yes:
        ans = input(f"{BD}Jalankan pembaruan sekarang? [y/N] {RS}").strip().lower()
        if ans not in ("y", "yes"):
            info("Pembaruan dibatalkan.")
            return

    if status["method"] == "git":
        warn("Perubahan lokal pada file yang dilacak git akan DITIMPA.")
        if _is_git_repo():
            updated = _update_via_git()
        else:
            updated = False
    else:
        updated = _update_via_zip()

    if not updated:
        err("Pembaruan gagal. Tidak ada perubahan layanan dilakukan.")
        return

    # Record the version we just moved to.
    _write_version_marker(status.get("remote", ""))

    # Refresh dependencies.
    _pip_install_requirements()

    # Update YARA rules
    _update_yara_rules()

    # Restart the service so the new application code takes effect.
    if assume_yes:
        do_restart = True
    elif interactive:
        ans = input(f"{BD}Restart layanan sekarang? [Y/n] {RS}").strip().lower()
        do_restart = ans in ("", "y", "yes")
    else:
        do_restart = True
    if do_restart:
        service_restart()

    print()
    ok("Pembaruan selesai.")
    warn("toolkit.py mungkin ikut diperbarui — jalankan ULANG toolkit.py "
         "untuk memakai versi terbaru.")


# ---------------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------------
_MENU = """\
 1) Regenerate Master Password (acak)
 2) Set Master Password (ketik manual)
 3) Regenerate SECRET_KEY
 4) Regenerate ENCRYPTION_KEY  (BERBAHAYA)
 5) Ubah Public URL / Google redirect URI
 6) Status layanan
 7) Restart layanan
 8) Stop layanan
 9) Start layanan
10) Lihat log layanan
11) Ringkasan konfigurasi
12) Jalankan backup manual
13) Cek & jalankan update
 0) Keluar"""


def menu() -> None:
    banner()
    while True:
        print(_MENU)
        choice = input(f"{BD}Pilih [0-13]: {RS}").strip()
        print()
        if choice == "1":
            regen_password()
        elif choice == "2":
            set_password()
        elif choice == "3":
            regen_secret()
        elif choice == "4":
            regen_encryption()
        elif choice == "5":
            set_public_url()
        elif choice == "6":
            service_status()
        elif choice == "7":
            service_restart()
        elif choice == "8":
            service_stop()
        elif choice == "9":
            service_start()
        elif choice == "10":
            service_logs()
        elif choice == "11":
            show_config()
        elif choice == "12":
            run_backup()
        elif choice == "13":
            do_update()
        elif choice == "0":
            info("Sampai jumpa.")
            return
        else:
            warn("Pilihan tidak dikenal.")
        print()


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------
def _print_help() -> None:
    print(__doc__)


def main(argv: list[str]) -> int:
    if not argv:
        try:
            menu()
        except (KeyboardInterrupt, EOFError):
            print()
            info("Dibatalkan.")
        return 0

    cmd = argv[0].lower()
    rest = argv[1:]
    try:
        if cmd in ("help", "-h", "--help"):
            _print_help()
        elif cmd == "regen-password":
            regen_password(interactive=False)
        elif cmd == "set-password":
            set_password(interactive=False)
        elif cmd == "regen-secret":
            regen_secret(interactive=False)
        elif cmd == "regen-encryption":
            regen_encryption(interactive=False)
        elif cmd == "set-public-url":
            set_public_url(rest[0] if rest else "", interactive=False)
        elif cmd == "status":
            service_status()
        elif cmd == "start":
            service_start()
        elif cmd == "stop":
            service_stop()
        elif cmd == "restart":
            service_restart()
        elif cmd == "logs":
            service_logs()
        elif cmd == "config":
            show_config()
        elif cmd == "backup":
            pid = int(rest[0]) if rest and rest[0].isdigit() else None
            run_backup(pid, interactive=False)
        elif cmd == "check-update":
            status = check_update(verbose=True)
            return 10 if status.get("available") else 0
        elif cmd == "update":
            assume_yes = ("--yes" in rest) or ("-y" in rest)
            do_update(assume_yes=assume_yes, interactive=not assume_yes)
        else:
            err(f"Perintah tidak dikenal: {cmd}")
            _print_help()
            return 2
    except KeyboardInterrupt:
        print()
        info("Dibatalkan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
