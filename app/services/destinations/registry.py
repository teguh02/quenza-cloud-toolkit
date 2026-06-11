"""Destination adapter registry and UI field specifications."""

from __future__ import annotations

from app.services.destinations.base import DestinationAdapter
from app.services.destinations.ftp_adapter import FtpAdapter
from app.services.destinations.gdrive_adapter import GDriveAdapter
from app.services.destinations.local_adapter import LocalAdapter
from app.services.destinations.s3_adapter import S3Adapter
from app.services.destinations.scp_adapter import ScpAdapter

_ADAPTERS: dict[str, type[DestinationAdapter]] = {
    LocalAdapter.type_key: LocalAdapter,
    S3Adapter.type_key: S3Adapter,
    GDriveAdapter.type_key: GDriveAdapter,
    FtpAdapter.type_key: FtpAdapter,
    ScpAdapter.type_key: ScpAdapter,
}


def get_adapter(dest_type: str, config: dict) -> DestinationAdapter | None:
    """Return an instantiated adapter for the given type, or None."""
    cls = _ADAPTERS.get(dest_type)
    if cls is None:
        return None
    return cls(config)


# UI metadata: what fields each destination type needs in forms.
# `secret=True` fields are rendered as password inputs and masked in views.
_SPECS: list[dict] = [
    {
        "key": "local",
        "label": "Local",
        "icon": "folder",
        "tone": "pastel-blue",
        "fg": "text-blue-500",
        "fields": [
            {"name": "path", "label": "Path Direktori", "type": "text",
             "placeholder": "mis. D:\\Backups atau /var/backups", "required": True},
        ],
    },
    {
        "key": "s3",
        "label": "Amazon S3",
        "icon": "cloud",
        "tone": "pastel-orange",
        "fg": "text-amber-500",
        "fields": [
            {"name": "bucket", "label": "Bucket", "type": "text", "required": True},
            {"name": "region", "label": "Region", "type": "text",
             "placeholder": "mis. ap-southeast-1", "required": False},
            {"name": "access_key", "label": "Access Key ID", "type": "text", "required": False},
            {"name": "secret_key", "label": "Secret Access Key", "type": "text",
             "required": False, "secret": True},
            {"name": "prefix", "label": "Prefix / Folder", "type": "text",
             "placeholder": "opsional", "required": False},
            {"name": "endpoint_url", "label": "Endpoint URL", "type": "text",
             "placeholder": "opsional (S3-compatible)", "required": False},
        ],
    },
    {
        "key": "gdrive",
        "label": "Google Drive",
        "icon": "cloud",
        "tone": "pastel-green",
        "fg": "text-brand-teal",
        "oauth": True,
        "fields": [
            {"name": "folder_id", "label": "Folder ID", "type": "text",
             "placeholder": "opsional (dibuat otomatis jika kosong)", "required": False},
        ],
    },
    {
        "key": "ftp",
        "label": "FTP",
        "icon": "cloud",
        "tone": "pastel-blue",
        "fg": "text-blue-500",
        "fields": [
            {"name": "host", "label": "Host", "type": "text", "required": True},
            {"name": "port", "label": "Port", "type": "text",
             "placeholder": "21", "required": False},
            {"name": "user", "label": "Username", "type": "text", "required": False},
            {"name": "password", "label": "Password", "type": "text",
             "required": False, "secret": True},
            {"name": "remote_dir", "label": "Direktori Tujuan", "type": "text",
             "placeholder": "mis. /backups", "required": False},
        ],
    },
    {
        "key": "scp",
        "label": "SCP / SSH",
        "icon": "cloud",
        "tone": "pastel-purple",
        "fg": "text-purple-500",
        "fields": [
            {"name": "host", "label": "Host", "type": "text", "required": True},
            {"name": "port", "label": "Port", "type": "text",
             "placeholder": "22", "required": False},
            {"name": "user", "label": "Username", "type": "text", "required": True},
            {"name": "auth_method", "label": "Metode Autentikasi", "type": "select",
             "options": [("password", "Password"), ("key", "Private Key")],
             "required": False},
            {"name": "password", "label": "Password", "type": "text",
             "required": False, "secret": True,
             "help": "Isi jika metode = Password"},
            {"name": "private_key", "label": "Private Key (PEM atau path)", "type": "textarea",
             "required": False, "secret": True,
             "help": "Isi jika metode = Private Key"},
            {"name": "passphrase", "label": "Passphrase Key", "type": "text",
             "required": False, "secret": True,
             "help": "Opsional, jika key terenkripsi"},
            {"name": "remote_dir", "label": "Direktori Tujuan", "type": "text",
             "placeholder": "mis. /var/backups", "required": False},
        ],
    },
]


def list_adapter_specs() -> list[dict]:
    """Return UI field specs for all destination types."""
    return _SPECS


def get_spec(dest_type: str) -> dict | None:
    """Return the UI spec for a single destination type."""
    for spec in _SPECS:
        if spec["key"] == dest_type:
            return spec
    return None
