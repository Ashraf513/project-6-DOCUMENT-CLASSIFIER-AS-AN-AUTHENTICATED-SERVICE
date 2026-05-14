"""
MinIO blob storage adapter.

Synchronous wrapper around the official minio-py client.
Used by the sftp-ingest worker (upload originals) and the inference worker
(download originals, upload overlays).

Bucket layout inside "documents":
    batches/{batch_id}/original/{filename}    ← raw TIFF from scanner
    batches/{batch_id}/overlay/{stem}.png     ← annotated result PNG
    quarantine/{batch_id}/{filename}          ← rejected files (non-TIFF, oversized)

Thread safety: Minio client is thread-safe; one BlobStorage instance per process.
"""

from __future__ import annotations

import io
import os
from datetime import timedelta
from pathlib import PurePosixPath

from minio import Minio
from minio.error import S3Error


BUCKET         = "documents"
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB hard cap


class BlobStorage:
    """Thin, testable wrapper around the MinIO Python client."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = BUCKET,
        secure: bool = False,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket
        self._ensure_bucket()

    # ── Bucket bootstrap ─────────────────────────────────────────────────────

    def _ensure_bucket(self) -> None:
        """Create the bucket on first use (idempotent — safe to call every startup)."""
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except S3Error as exc:
            raise RuntimeError(
                f"Could not ensure MinIO bucket '{self._bucket}' exists: {exc}"
            ) from exc

    # ── Key helpers (static — used by callers to build consistent paths) ─────

    @staticmethod
    def original_key(batch_id: str, filename: str) -> str:
        """Return the canonical MinIO key for a raw uploaded TIFF."""
        return f"batches/{batch_id}/original/{filename}"

    @staticmethod
    def overlay_key(batch_id: str, filename: str) -> str:
        """Return the canonical MinIO key for the annotated result PNG."""
        stem = PurePosixPath(filename).stem
        return f"batches/{batch_id}/overlay/{stem}.png"

    @staticmethod
    def quarantine_key(batch_id: str, filename: str) -> str:
        """Return the MinIO key for a file moved to quarantine."""
        return f"quarantine/{batch_id}/{filename}"

    # ── Core operations ──────────────────────────────────────────────────────

    def upload(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload *data* under *key* in the bucket.

        Returns the key on success so callers can chain it.
        Raises RuntimeError on MinIO failure.
        """
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(
                f"File too large: {len(data):,} bytes (hard cap {MAX_FILE_BYTES:,})"
            )
        try:
            self._client.put_object(
                self._bucket,
                key,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        except S3Error as exc:
            raise RuntimeError(
                f"MinIO upload failed for key '{key}': {exc}"
            ) from exc
        return key

    def download(self, key: str) -> bytes:
        """
        Download and return the raw bytes stored at *key*.

        Raises RuntimeError if the object is missing or MinIO is unreachable.
        """
        response = None
        try:
            response = self._client.get_object(self._bucket, key)
            return response.read()
        except S3Error as exc:
            raise RuntimeError(
                f"MinIO download failed for key '{key}': {exc}"
            ) from exc
        finally:
            if response is not None:
                try:
                    response.close()
                    response.release_conn()
                except Exception:
                    pass

    def exists(self, key: str) -> bool:
        """
        Return True if *key* is already stored in the bucket.

        Used for idempotency: if the sftp-ingest worker restarts it skips
        files that are already present in MinIO.
        """
        try:
            self._client.stat_object(self._bucket, key)
            return True
        except S3Error:
            return False

    def presigned_url(self, key: str, expires_seconds: int = 3_600) -> str:
        """
        Generate a temporary presigned GET URL for *key*.

        Allows API clients to download files directly from MinIO without
        routing the bytes through the API container.
        """
        try:
            return self._client.presigned_get_object(
                self._bucket,
                key,
                expires=timedelta(seconds=expires_seconds),
            )
        except S3Error as exc:
            raise RuntimeError(
                f"Could not generate presigned URL for '{key}': {exc}"
            ) from exc


# ── Factory ──────────────────────────────────────────────────────────────────

def get_blob_storage() -> BlobStorage:
    """
    Build a BlobStorage instance from environment variables and Vault secrets.

    MINIO_ENDPOINT is operational config (not a secret) — read from env.
    MINIO_ACCESS_KEY / MINIO_SECRET_KEY are secrets — fetched from Vault.

    Call once at process startup and reuse the instance.
    """
    from app.infra.vault import get_secret

    endpoint   = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    access_key = get_secret("MINIO_ACCESS_KEY")
    secret_key = get_secret("MINIO_SECRET_KEY")

    return BlobStorage(endpoint=endpoint, access_key=access_key, secret_key=secret_key)
