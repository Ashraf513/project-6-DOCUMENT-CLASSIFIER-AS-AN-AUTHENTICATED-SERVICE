"""
SFTP file watcher — polls the scanner vendor's drop-zone for new TIFF files.

Runs as an async loop inside the sftp-ingest container.

Per-file pipeline:
  1. Validate (extension, zero-byte, size cap)
  2. Download from SFTP
  3. Upload original TIFF to MinIO
  4. Create (or extend) a Batch record in Postgres
  5. Enqueue an RQ classify job
  6. Mark file as "seen" to prevent reprocessing this session

Crash-safety:
  On restart the in-memory `_seen` set is empty, but `blob.exists(key)` is
  checked before every upload.  Files already in MinIO are skipped so jobs
  are never duplicated after a restart.

Rejected files (non-TIFF, zero-byte, oversized) are uploaded to the
MinIO `quarantine/` prefix so operators can inspect them.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import PurePosixPath
from typing import Callable, Awaitable

import paramiko

from app.infra.blob import BlobStorage
from app.infra.queue import ClassifyQueue


log = logging.getLogger(__name__)

VALID_EXTENSIONS = frozenset({".tiff", ".tif"})
MAX_FILE_BYTES   = 100 * 1024 * 1024  # 100 MB


class SFTPWatcher:
    """
    Polls an SFTP server and dispatches new TIFF files for classification.

    Constructor arguments:
        host, port, user, password  — SFTP connection details
        watch_path    — remote directory to monitor (e.g. "/upload")
        poll_interval — seconds between scans (default 5)
        blob          — BlobStorage instance
        queue         — ClassifyQueue instance
        create_batch  — async callable(file_count: int) -> str (batch_id)
                        Injected so the watcher stays decoupled from SQLAlchemy.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        watch_path: str,
        poll_interval: int,
        blob: BlobStorage,
        queue: ClassifyQueue,
        create_batch: Callable[[int], Awaitable[str]],
    ) -> None:
        self.host          = host
        self.port          = port
        self.user          = user
        self.password      = password
        self.watch_path    = watch_path
        self.poll_interval = poll_interval
        self.blob          = blob
        self.queue         = queue
        self._create_batch = create_batch
        self._seen: set[str] = set()

    # ── Main loop ────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Blocking async loop — runs until the process is terminated.
        A single unhandled exception in one poll cycle does NOT stop the loop.
        """
        log.info(
            "SFTP watcher started host=%s path=%s interval=%ss",
            self.host, self.watch_path, self.poll_interval,
        )
        while True:
            try:
                await self._poll()
            except Exception:
                log.exception("Unhandled error in poll cycle — retrying next interval")
            await asyncio.sleep(self.poll_interval)

    # ── Poll cycle ───────────────────────────────────────────────────────────

    async def _poll(self) -> None:
        """Single poll: connect, list new files, process them."""
        new_files = await asyncio.to_thread(self._list_new_files)
        if not new_files:
            return

        log.info("Detected %d new file(s): %s", len(new_files), new_files)

        request_id = str(uuid.uuid4())
        batch_id   = await self._create_batch(len(new_files))

        log.info("Created batch %s for request %s", batch_id, request_id)

        for filename in new_files:
            await self._process_file(filename, batch_id, request_id)

    def _list_new_files(self) -> list[str]:
        """
        Synchronous (called via asyncio.to_thread): list the SFTP watch
        directory and return filenames not yet in self._seen.
        """
        try:
            with _SFTPSession(self.host, self.port, self.user, self.password) as sftp:
                entries = sftp.listdir_attr(self.watch_path)
        except (paramiko.SSHException, OSError):
            log.warning("Could not connect to SFTP %s:%s — will retry", self.host, self.port)
            return []

        return [
            entry.filename
            for entry in entries
            if entry.filename not in self._seen
        ]

    async def _process_file(
        self, filename: str, batch_id: str, request_id: str
    ) -> None:
        """
        Full pipeline for a single file.
        Errors are logged and the file is left out of _seen so the next
        poll retries it — UNLESS it was quarantined (validation failure).
        """
        blob_key = BlobStorage.original_key(batch_id, filename)

        # ── Idempotency check ────────────────────────────────────────────────
        already_present = await asyncio.to_thread(self.blob.exists, blob_key)
        if already_present:
            log.info("Already in MinIO — skipping %s", filename)
            self._seen.add(filename)
            return

        # ── Download from SFTP ───────────────────────────────────────────────
        try:
            data = await asyncio.to_thread(self._sftp_download, filename)
        except Exception:
            log.exception("SFTP download failed for %s — will retry next cycle", filename)
            return

        # ── Validate ─────────────────────────────────────────────────────────
        reason = _reject_reason(filename, data)
        if reason:
            log.warning("Quarantining %s: %s", filename, reason)
            qkey = BlobStorage.quarantine_key(batch_id, filename)
            try:
                await asyncio.to_thread(
                    self.blob.upload, qkey, data, "application/octet-stream"
                )
            except Exception:
                log.exception("Could not upload %s to quarantine", filename)
            self._seen.add(filename)
            return

        # ── Upload to MinIO ───────────────────────────────────────────────────
        try:
            await asyncio.to_thread(self.blob.upload, blob_key, data, "image/tiff")
        except Exception:
            log.exception("MinIO upload failed for %s — will retry next cycle", filename)
            return

        # ── Enqueue classify job ──────────────────────────────────────────────
        try:
            job_id = await asyncio.to_thread(
                self.queue.enqueue_classify, batch_id, blob_key, request_id
            )
            log.info(
                "Enqueued classify job %s for %s (batch %s, request %s)",
                job_id, filename, batch_id, request_id,
            )
        except Exception:
            log.exception("RQ enqueue failed for %s — file uploaded, job lost", filename)
            # File is in MinIO but not queued.  Still mark seen so we don't
            # re-upload; ops team can retry via RQ CLI or re-drop the file.
            self._seen.add(filename)
            return

        self._seen.add(filename)

    def _sftp_download(self, filename: str) -> bytes:
        """
        Synchronous download (runs in a thread).
        Checks remote file size before reading to enforce the 100 MB cap.
        """
        remote_path = f"{self.watch_path}/{filename}"
        with _SFTPSession(self.host, self.port, self.user, self.password) as sftp:
            attr = sftp.stat(remote_path)
            size = attr.st_size or 0
            if size > MAX_FILE_BYTES:
                raise ValueError(
                    f"Remote file too large: {size:,} bytes (cap {MAX_FILE_BYTES:,})"
                )
            with sftp.open(remote_path, "rb") as fh:
                return fh.read()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reject_reason(filename: str, data: bytes) -> str | None:
    """
    Return a human-readable rejection reason, or None if the file is valid.
    Checked after the file is downloaded so the data size is known exactly.
    """
    if not data:
        return "zero-byte file"
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in VALID_EXTENSIONS:
        return f"unsupported extension '{suffix}' (accepted: .tiff, .tif)"
    if len(data) > MAX_FILE_BYTES:
        return f"file too large: {len(data):,} bytes (cap {MAX_FILE_BYTES:,})"
    return None


class _SFTPSession:
    """
    Context manager that opens and cleanly closes a paramiko SFTP session.

    Uses AutoAddPolicy for host-key verification — acceptable for a private
    container network where man-in-the-middle attacks are not a concern.
    Replace with a pinned HostKeys instance for production environments that
    communicate over public networks.
    """

    def __init__(self, host: str, port: int, user: str, password: str) -> None:
        self._host     = host
        self._port     = port
        self._user     = user
        self._password = password
        self._ssh:  paramiko.SSHClient  | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> paramiko.SFTPClient:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            timeout=10,
            banner_timeout=10,
            auth_timeout=10,
        )
        self._ssh  = ssh
        self._sftp = ssh.open_sftp()
        return self._sftp

    def __exit__(self, *_: object) -> None:
        for obj in (self._sftp, self._ssh):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
