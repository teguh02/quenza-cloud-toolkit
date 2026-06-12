"""Database dump service: run mysqldump / pg_dump via subprocess.

Design goals:
  * Never crash the whole backup if a dump tool is missing or fails.
    Instead return a structured DumpResult with ok=False and a clear
    message so the orchestrator can mark just that source as failed.
  * Stream stdout to a .sql file on disk.
  * Pass DB passwords via the environment (not argv) where possible to
    avoid leaking them in process listings.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

# Hard cap so a hung dump cannot block the worker forever.
_DUMP_TIMEOUT_SECONDS = 60 * 30  # 30 minutes


@dataclass
class DumpResult:
    """Outcome of a database dump."""

    ok: bool
    output_path: str = ""
    error: str | None = None


def _resolve_tool(configured: str) -> str | None:
    """Return an executable path for a tool, or None if not found."""
    # If configured value is an existing file, use it directly.
    if configured and os.path.isfile(configured):
        return configured
    # Otherwise search PATH.
    found = shutil.which(configured)
    return found


def dump_mysql(
    *,
    host: str,
    port: int | None,
    name: str,
    user: str,
    password: str,
    out_dir: str,
    filename: str | None = None,
) -> DumpResult:
    """Dump a MySQL database to a .sql file using mysqldump."""
    tool = _resolve_tool(settings.mysqldump_path)
    if not tool:
        return DumpResult(
            ok=False,
            error=(
                "mysqldump tidak ditemukan. Pasang MySQL client tools atau "
                "atur MYSQLDUMP_PATH di .env."
            ),
        )

    if not name:
        return DumpResult(ok=False, error="Nama database MySQL kosong.")

    out_file = Path(out_dir) / (filename or f"mysql_{name}.sql")
    args = [
        tool,
        f"--host={host or '127.0.0.1'}",
        f"--port={int(port) if port else 3306}",
        "--single-transaction",
        "--quick",
        "--skip-lock-tables",
    ]
    if user:
        args.append(f"--user={user}")
    args.append(name)

    env = os.environ.copy()
    if password:
        # mysqldump reads MYSQL_PWD from the environment.
        env["MYSQL_PWD"] = password

    return _run_dump(args, out_file, env)


def dump_postgres(
    *,
    host: str,
    port: int | None,
    name: str,
    user: str,
    password: str,
    out_dir: str,
    filename: str | None = None,
) -> DumpResult:
    """Dump a PostgreSQL database to a .sql file using pg_dump."""
    tool = _resolve_tool(settings.pg_dump_path)
    if not tool:
        return DumpResult(
            ok=False,
            error=(
                "pg_dump tidak ditemukan. Pasang PostgreSQL client tools atau "
                "atur PG_DUMP_PATH di .env."
            ),
        )

    if not name:
        return DumpResult(ok=False, error="Nama database PostgreSQL kosong.")

    out_file = Path(out_dir) / (filename or f"postgres_{name}.sql")
    args = [
        tool,
        f"--host={host or '127.0.0.1'}",
        f"--port={int(port) if port else 5432}",
        "--no-owner",
        "--no-privileges",
    ]
    if user:
        args.append(f"--username={user}")
    args.append(name)

    env = os.environ.copy()
    if password:
        # pg_dump reads PGPASSWORD from the environment.
        env["PGPASSWORD"] = password

    return _run_dump(args, out_file, env)


def _run_dump(args: list[str], out_file: Path, env: dict) -> DumpResult:
    """Execute a dump command, streaming stdout into out_file."""
    try:
        out_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return DumpResult(ok=False, error=f"Gagal menyiapkan direktori dump: {exc}")

    try:
        with open(out_file, "wb") as fh:
            proc = subprocess.run(
                args,
                stdout=fh,
                stderr=subprocess.PIPE,
                env=env,
                timeout=_DUMP_TIMEOUT_SECONDS,
                check=False,
            )
    except FileNotFoundError:
        return DumpResult(ok=False, error="Executable dump tidak dapat dijalankan.")
    except subprocess.TimeoutExpired:
        _cleanup(out_file)
        return DumpResult(ok=False, error="Dump melebihi batas waktu (timeout).")
    except OSError as exc:
        _cleanup(out_file)
        return DumpResult(ok=False, error=f"Kesalahan menjalankan dump: {exc}")

    if proc.returncode != 0:
        _cleanup(out_file)
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        # Keep the message concise.
        snippet = stderr.splitlines()[-1] if stderr else f"exit code {proc.returncode}"
        return DumpResult(ok=False, error=f"Dump gagal: {snippet}")

    # Empty output usually means an auth/connection problem that returned 0.
    try:
        if out_file.stat().st_size == 0:
            _cleanup(out_file)
            return DumpResult(ok=False, error="Hasil dump kosong (periksa kredensial).")
    except OSError:
        pass

    return DumpResult(ok=True, output_path=str(out_file))


def _cleanup(path: Path) -> None:
    """Remove a partial dump file, ignoring errors."""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def tool_availability() -> dict[str, bool]:
    """Report whether each dump tool is currently resolvable."""
    return {
        "mysqldump": _resolve_tool(settings.mysqldump_path) is not None,
        "pg_dump": _resolve_tool(settings.pg_dump_path) is not None,
    }


def test_mysql_connection(
    *,
    host: str,
    port: int | None,
    name: str,
    user: str,
    password: str,
) -> tuple[bool, str]:
    tool = _resolve_tool(settings.mysqldump_path)
    if not tool:
        return False, "mysqldump tidak ditemukan."

    args = [
        tool,
        f"--host={host or '127.0.0.1'}",
        f"--port={int(port) if port else 3306}",
        "--no-data",
        "--where=1=0",
    ]
    if user:
        args.append(f"--user={user}")
    args.append(name)

    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password

    try:
        proc = subprocess.run(args, capture_output=True, env=env, timeout=15)
        if proc.returncode == 0:
            return True, "Koneksi berhasil."
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        return False, stderr.splitlines()[-1] if stderr else "Koneksi gagal (exit code != 0)"
    except Exception as exc:
        return False, f"Error internal: {exc}"


def test_postgres_connection(
    *,
    host: str,
    port: int | None,
    name: str,
    user: str,
    password: str,
) -> tuple[bool, str]:
    tool = _resolve_tool("pg_isready")
    if tool:
        args = [tool, f"--host={host or '127.0.0.1'}", f"--port={int(port) if port else 5432}"]
        if user:
            args.append(f"--username={user}")
        if name:
            args.append(f"--dbname={name}")
        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password
        try:
            proc = subprocess.run(args, capture_output=True, env=env, timeout=15)
            if proc.returncode == 0:
                return True, "Koneksi berhasil."
            err = proc.stderr.decode("utf-8", errors="replace").strip() or proc.stdout.decode("utf-8", errors="replace").strip()
            return False, err or "Koneksi gagal."
        except Exception:
            pass # Fallback to pg_dump

    tool = _resolve_tool(settings.pg_dump_path)
    if not tool:
        return False, "pg_dump tidak ditemukan."
    args = [
        tool,
        f"--host={host or '127.0.0.1'}",
        f"--port={int(port) if port else 5432}",
        "--schema-only",
        "--table=quenza_test_table_xyz123",
    ]
    if user:
        args.append(f"--username={user}")
    args.append(name)

    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password

    try:
        proc = subprocess.run(args, capture_output=True, env=env, timeout=15)
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 or "no matching tables" in err.lower() or "did not find any relation" in err.lower():
            return True, "Koneksi berhasil."
        return False, err.splitlines()[-1] if err else "Koneksi gagal."
    except Exception as exc:
        return False, f"Error internal: {exc}"
