"""Destination adapters package.

Each adapter implements a common interface for uploading a backup archive
to a target (Local, S3, Google Drive). Optional third-party SDKs
are imported lazily inside each adapter so the app runs even when a given
SDK is not installed; in that case the adapter reports a clear error.
"""

from app.services.destinations.base import (
    ArchiveEntry,
    DestinationAdapter,
    DownloadResult,
    ListResult,
    TestResult,
    UploadResult,
)
from app.services.destinations.registry import get_adapter, list_adapter_specs

__all__ = [
    "ArchiveEntry",
    "DestinationAdapter",
    "DownloadResult",
    "ListResult",
    "TestResult",
    "UploadResult",
    "get_adapter",
    "list_adapter_specs",
]
