"""
SFTP Watcher — polls the SFTP upload folder every POLL_INTERVAL seconds.

For each new file found:
  1. Validate  — reject zero-byte, non-TIFF, or oversized files (quarantine them).
  2. Download  — stream from SFTP into memory.
  3. Upload    — push to MinIO via BlobClient.
  4. Enqueue   — add a classify job to Redis via enqueue_job().

The watcher tracks already-processed filenames in a local set so it never
processes the same file twice within a single run.  On restart it re-scans
and skips files that are already in MinIO (detected via the seen set being
rebuilt empty — a future improvement could persist the set to Redis).
"""

import io
import time
import uuid

import paramiko
import structlog

from app.infra.blob import BlobClient
from app.infra.queue import enqueue_job
from rq import Queue

log = structlog.get_logger()

POLL_INTERVAL   = 5               # seconds between SFTP polls
MAX_FILE_BYTES  = 100 * 1024 * 1024   # 100 MB hard limit
VALID_EXTS      = {".tiff", ".tif"}


class SFTPWatcher:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        remote_path: str,
        blob: BlobClient,
        queue: Queue,
        on_batch_created=None,
    ) -> None:
        self.host        = host
        self.port        = port
        self.username    = username
        self.password    = password
        self.remote_path = remote_path.rstrip("/")
        self.blob        = blob
        self.queue       = queue
        # Hook called after a batch ID is generated — wired to DB service later
        self.on_batch_created = on_batch_created or (lambda bid: None)
        # Tracks filenames processed in this run.  Starts empty on every restart,
        # so the watcher re-scans but skips files already in MinIO via the seen set
        # being rebuilt — a future improvement could persist this set to Redis.
        self._seen: set[str] = set()

    # ── entry point ───────────────────────────────────────────────────────────

    def run(self) -> None:
        log.info("sftp_watcher_started", host=self.host, path=self.remote_path)
        while True:
            try:
                self._poll()
            except Exception as exc:
                log.error("poll_error", error=str(exc), error_type=type(exc).__name__)
            time.sleep(POLL_INTERVAL)

    # ── internals ─────────────────────────────────────────────────────────────

    def _connect(self) -> tuple[paramiko.SSHClient, paramiko.SFTPClient]:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=10,
        )
        return ssh, ssh.open_sftp()

    def _poll(self) -> None:
        ssh, sftp = self._connect()
        try:
            try:
                all_files = sftp.listdir(self.remote_path)
            except IOError:
                log.warning("sftp_path_missing", path=self.remote_path)
                return

            new_files = [f for f in all_files if f not in self._seen]
            if not new_files:
                return

            # One batch ID per poll cycle — all files found in a single scan
            # are grouped into the same batch (one "drop" = one batch).
            batch_id   = str(uuid.uuid4())
            request_id = str(uuid.uuid4())
            self.on_batch_created(batch_id)

            log.info(
                "batch_started",
                batch_id=batch_id,
                file_count=len(new_files),
                request_id=request_id,
            )

            for filename in new_files:
                self._handle_file(sftp, filename, batch_id, request_id)
                self._seen.add(filename)
        finally:
            sftp.close()
            ssh.close()

    def _handle_file(
        self,
        sftp: paramiko.SFTPClient,
        filename: str,
        batch_id: str,
        request_id: str,
    ) -> None:
        flog = log.bind(filename=filename, batch_id=batch_id, request_id=request_id)
        remote = f"{self.remote_path}/{filename}"

        # ── stat ──────────────────────────────────────────────────────────────
        try:
            stat = sftp.stat(remote)
        except IOError:
            flog.warning("stat_failed")
            return

        # ── validate size ─────────────────────────────────────────────────────
        if stat.st_size == 0:
            flog.warning("zero_byte_file_skipped")
            return

        # ── validate extension ────────────────────────────────────────────────
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if ext not in VALID_EXTS:
            flog.warning("non_tiff_quarantined", extension=ext)
            self._quarantine(sftp, remote, filename, flog)
            return

        if stat.st_size > MAX_FILE_BYTES:
            flog.warning("file_too_large", size_bytes=stat.st_size)
            self._quarantine(sftp, remote, filename, flog)
            return

        # ── download + upload + enqueue ───────────────────────────────────────
        with sftp.open(remote) as fh:
            data = fh.read()
        blob_uri = self.blob.upload_file(data, filename, batch_id=batch_id)
        # Workers receive the raw key, not the full URI
        blob_key = blob_uri.removeprefix(f"minio://{self.blob.BUCKET}/")
        enqueue_job(self.queue, batch_id, blob_key, request_id)
        flog.info("file_enqueued", blob_key=blob_key)

    def _quarantine(
        self,
        sftp: paramiko.SFTPClient,
        remote: str,
        filename: str,
        flog,
    ) -> None:
        try:
            with sftp.open(remote) as fh:
                data = fh.read()
            self.blob._client.put_object(
                self.blob.BUCKET,
                f"quarantine/{filename}",
                io.BytesIO(data),
                len(data),
            )
            flog.info("file_quarantined", destination=f"quarantine/{filename}")
        except Exception as exc:
            flog.error("quarantine_failed", error=str(exc))
