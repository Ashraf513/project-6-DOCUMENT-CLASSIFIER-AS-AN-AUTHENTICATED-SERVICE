"""
Blob storage adapter — wraps MinIO (S3-compatible).

Public interface used by the rest of the codebase:
    upload_file(file_bytes, filename, batch_id)  -> "minio://documents/batches/..."
    download_file(path)                          -> bytes
    generate_path(filename, batch_id)            -> "batches/{id}/original/{name}"
    upload_overlay(overlay_bytes, original_key)  -> "minio://documents/batches/..."
    presigned_url(path, expires_minutes)         -> https://...

All paths stored in the DB use the full "minio://bucket/key" URI form so
the bucket name is never assumed anywhere else in the codebase.
"""

import io
import uuid
from datetime import timedelta
from pathlib import PurePosixPath

import structlog
from minio import Minio

log = structlog.get_logger()

BUCKET = "documents"


class BlobClient:
    BUCKET = BUCKET   # exposed as class attribute so callers can use instance.BUCKET

    def __init__(self, endpoint: str, access_key: str, secret_key: str) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )
        # MinIO starts with no buckets; creating it here means every method
        # can assume the bucket exists without its own guard.
        self._ensure_bucket()

    # ── public ────────────────────────────────────────────────────────────────

    def generate_path(self, filename: str, batch_id: str | None = None) -> str:
        """Return the MinIO object key for an original document."""
        bid = batch_id or str(uuid.uuid4())
        return f"batches/{bid}/original/{filename}"

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        batch_id: str | None = None,
        content_type: str = "image/tiff",
    ) -> str:
        """Upload document bytes; return full URI: minio://documents/<key>."""
        key = self.generate_path(filename, batch_id)
        self._client.put_object(
            BUCKET,
            key,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type,
        )
        # Embed bucket name in every stored URI so no other code needs to
        # hardcode or assume it — if the bucket name changes, DB rows still decode.
        uri = f"minio://{BUCKET}/{key}"
        log.info("file_uploaded", uri=uri, size_bytes=len(file_bytes))
        return uri

    def download_file(self, path: str) -> bytes:
        """Download by URI ("minio://bucket/key") or raw key."""
        key = self._parse_key(path)
        resp = self._client.get_object(BUCKET, key)
        try:
            data = resp.read()
        finally:
            resp.close()
            resp.release_conn()
        log.info("file_downloaded", key=key, size_bytes=len(data))
        return data

    def upload_overlay(self, overlay_bytes: bytes, original_key: str) -> str:
        """Upload annotated overlay PNG; mirrors the original key path."""
        raw_key = self._parse_key(original_key)
        # Mirror the original path: batches/<id>/original/doc.tiff
        #                       →   batches/<id>/overlay/doc.png
        overlay_key = raw_key.replace("/original/", "/overlay/")
        overlay_key = str(PurePosixPath(overlay_key).with_suffix(".png"))
        self._client.put_object(
            BUCKET,
            overlay_key,
            io.BytesIO(overlay_bytes),
            length=len(overlay_bytes),
            content_type="image/png",
        )
        uri = f"minio://{BUCKET}/{overlay_key}"
        log.info("overlay_uploaded", uri=uri)
        return uri

    def presigned_url(self, path: str, expires_minutes: int = 60) -> str:
        """Generate a temporary download URL (default: 1 hour)."""
        key = self._parse_key(path)
        return self._client.presigned_get_object(
            BUCKET, key, expires=timedelta(minutes=expires_minutes)
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(BUCKET):
            self._client.make_bucket(BUCKET)
            log.info("bucket_created", bucket=BUCKET)

    @staticmethod
    def _parse_key(path: str) -> str:
        """Strip 'minio://bucket/' prefix if present."""
        if path.startswith("minio://"):
            # "minio://documents/batches/..." -> "batches/..."
            stripped = path.removeprefix("minio://")
            parts = stripped.split("/", 1)
            if len(parts) < 2 or not parts[1]:
                raise ValueError(f"Malformed MinIO URI — expected 'minio://bucket/key', got: '{path}'")
            return parts[1]
        return path
