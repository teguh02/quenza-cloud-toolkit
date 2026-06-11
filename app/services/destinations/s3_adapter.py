"""Amazon S3 (and S3-compatible) destination adapter using boto3."""

from __future__ import annotations

from pathlib import Path

from app.services.destinations.base import (
    ArchiveEntry,
    DestinationAdapter,
    DownloadResult,
    ListResult,
    TestResult,
    UploadResult,
)


def _is_archive(name: str) -> bool:
    n = name.lower()
    return n.endswith(".zip") or n.endswith(".tar.gz") or n.endswith(".tgz")


class S3Adapter(DestinationAdapter):
    """Upload archives to an S3 bucket.

    Config:
        bucket (str): target bucket name.
        region (str): AWS region (optional).
        access_key (str), secret_key (str): credentials.
        prefix (str): optional key prefix (folder).
        endpoint_url (str): optional, for S3-compatible providers.
    """

    type_key = "s3"
    label = "Amazon S3"

    def _client(self):
        """Build a boto3 S3 client. Raises on missing SDK/config."""
        import boto3  # lazy import

        kwargs = {}
        region = (self.config.get("region") or "").strip()
        endpoint = (self.config.get("endpoint_url") or "").strip()
        access = (self.config.get("access_key") or "").strip()
        secret = (self.config.get("secret_key") or "").strip()

        if region:
            kwargs["region_name"] = region
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        if access and secret:
            kwargs["aws_access_key_id"] = access
            kwargs["aws_secret_access_key"] = secret

        return boto3.client("s3", **kwargs)

    def _key(self, remote_name: str) -> str:
        prefix = (self.config.get("prefix") or "").strip().strip("/")
        return f"{prefix}/{remote_name}" if prefix else remote_name

    def upload(self, local_path: str, remote_name: str) -> UploadResult:
        bucket = (self.config.get("bucket") or "").strip()
        if not bucket:
            return UploadResult(ok=False, error="Nama bucket S3 belum diatur.")

        try:
            client = self._client()
        except ImportError:
            return UploadResult(
                ok=False, error="Library 'boto3' belum terpasang (pip install boto3)."
            )
        except Exception as exc:  # pragma: no cover - config errors
            return UploadResult(ok=False, error=f"Gagal inisialisasi S3: {exc}")

        key = self._key(remote_name)
        try:
            client.upload_file(local_path, bucket, key)
        except Exception as exc:
            return UploadResult(ok=False, error=f"Upload S3 gagal: {exc}")

        return UploadResult(ok=True, location=f"s3://{bucket}/{key}")

    def test_connection(self) -> TestResult:
        bucket = (self.config.get("bucket") or "").strip()
        if not bucket:
            return TestResult(ok=False, message="Nama bucket S3 belum diatur.")

        try:
            client = self._client()
        except ImportError:
            return self._missing_sdk("boto3", "pip install boto3")
        except Exception as exc:  # pragma: no cover
            return TestResult(ok=False, message=f"Gagal inisialisasi S3: {exc}")

        try:
            client.head_bucket(Bucket=bucket)
        except Exception as exc:
            return TestResult(ok=False, message=f"Tidak dapat mengakses bucket: {exc}")

        return TestResult(ok=True, message=f"Bucket '{bucket}' dapat diakses.")

    def list_archives(self) -> ListResult:
        bucket = (self.config.get("bucket") or "").strip()
        if not bucket:
            return ListResult(ok=False, error="Nama bucket S3 belum diatur.")
        try:
            client = self._client()
        except ImportError:
            return ListResult(ok=False, error="Library 'boto3' belum terpasang.")
        except Exception as exc:  # pragma: no cover
            return ListResult(ok=False, error=f"Gagal inisialisasi S3: {exc}")

        prefix = (self.config.get("prefix") or "").strip().strip("/")
        kwargs = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix + "/"

        entries: list[ArchiveEntry] = []
        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(**kwargs):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    name = key.rsplit("/", 1)[-1]
                    if not _is_archive(name):
                        continue
                    modified = ""
                    lm = obj.get("LastModified")
                    if lm is not None:
                        modified = lm.strftime("%Y-%m-%d %H:%M")
                    entries.append(
                        ArchiveEntry(
                            name=name,
                            size=int(obj.get("Size", 0)),
                            modified=modified,
                            ref=key,
                        )
                    )
        except Exception as exc:
            return ListResult(ok=False, error=f"Gagal mendaftar objek S3: {exc}")

        entries.sort(key=lambda e: e.modified, reverse=True)
        return ListResult(ok=True, entries=entries)

    def download(self, ref: str, dest_dir: str) -> DownloadResult:
        bucket = (self.config.get("bucket") or "").strip()
        if not bucket:
            return DownloadResult(ok=False, error="Nama bucket S3 belum diatur.")
        try:
            client = self._client()
        except ImportError:
            return DownloadResult(ok=False, error="Library 'boto3' belum terpasang.")
        except Exception as exc:  # pragma: no cover
            return DownloadResult(ok=False, error=f"Gagal inisialisasi S3: {exc}")

        try:
            out_dir = Path(dest_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            name = ref.rsplit("/", 1)[-1]
            out_path = out_dir / name
            client.download_file(bucket, ref, str(out_path))
        except Exception as exc:
            return DownloadResult(ok=False, error=f"Gagal mengunduh dari S3: {exc}")

        return DownloadResult(ok=True, local_path=str(out_path))
