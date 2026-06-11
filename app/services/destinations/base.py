"""Base types and interface for destination adapters."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UploadResult:
    """Outcome of an upload to a destination."""

    ok: bool
    location: str = ""        # remote path/key/URL where the file landed
    error: str | None = None


@dataclass
class TestResult:
    """Outcome of a connectivity/credentials test."""

    ok: bool
    message: str = ""


@dataclass
class ArchiveEntry:
    """A backup archive available at a destination."""

    name: str
    size: int = 0
    modified: str = ""
    ref: str = ""  # opaque reference used by download (key/path/id)


@dataclass
class ListResult:
    """Outcome of listing archives at a destination."""

    ok: bool
    entries: list[ArchiveEntry] = field(default_factory=list)
    error: str | None = None


@dataclass
class DownloadResult:
    """Outcome of downloading an archive from a destination."""

    ok: bool
    local_path: str = ""
    error: str | None = None


class DestinationAdapter:
    """Common interface for all destinations.

    Subclasses receive the destination's parsed config dict and implement
    `upload` and `test_connection`. Implementations must never raise for
    expected failures; return a result with ok=False instead.

    Restore support (Phase 5) adds `list_archives` and `download`. Adapters
    that cannot support restore return ok=False with a clear message.
    """

    #: machine key, e.g. "s3"
    type_key: str = "base"
    #: human label
    label: str = "Base"

    def __init__(self, config: dict):
        self.config = config or {}

    def upload(self, local_path: str, remote_name: str) -> UploadResult:
        """Upload `local_path` to the destination as `remote_name`."""
        raise NotImplementedError

    def test_connection(self) -> TestResult:
        """Validate configuration and connectivity."""
        raise NotImplementedError

    def list_archives(self) -> ListResult:
        """List archives available for restore at this destination."""
        return ListResult(
            ok=False, error="Destinasi ini belum mendukung daftar arsip."
        )

    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        """Download an archive (by `ref`) into `dest_dir`."""
        return DownloadResult(
            ok=False, error="Destinasi ini belum mendukung unduh arsip."
        )

    # -- helpers ------------------------------------------------------------
    def _missing_sdk(self, package: str, install_hint: str) -> TestResult:
        return TestResult(
            ok=False,
            message=(
                f"Library '{package}' belum terpasang. Jalankan: {install_hint}"
            ),
        )
