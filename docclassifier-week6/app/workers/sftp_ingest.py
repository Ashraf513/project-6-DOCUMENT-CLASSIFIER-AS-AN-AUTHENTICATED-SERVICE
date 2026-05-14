"""
Entry point for the sftp-ingest container.

docker-compose command:
    python -m app.workers.sftp_ingest

Flow:
  1. Build BlobStorage — reads MINIO_ENDPOINT from env, credentials from Vault.
  2. Build ClassifyQueue — reads REDIS_URL from env.
  3. Read SFTP config from env vars (set by docker-compose, not Vault).
  4. Start SFTPWatcher with an async create_batch callback that writes a Batch
     row to Postgres before any jobs are enqueued.

All secrets (MINIO_ACCESS_KEY, MINIO_SECRET_KEY) are fetched from Vault by
get_blob_storage() at startup — this module never reads .env directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


# ── Batch creation callback ───────────────────────────────────────────────────

async def _create_batch(file_count: int) -> str:
    """
    Async callback injected into SFTPWatcher.

    Creates one Batch row per poll cycle and returns its UUID.
    Uses AsyncSessionLocal so it runs in the same event loop as the watcher.
    """
    from app.db.session import AsyncSessionLocal
    from app.db.models import Batch

    batch_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(Batch(id=batch_id, file_count=file_count))

    log.info("batch_created id=%s file_count=%d", batch_id, file_count)
    return batch_id


# ── Main entry point ──────────────────────────────────────────────────────────

async def _main() -> None:
    from app.infra.blob import get_blob_storage
    from app.infra.queue import get_classify_queue
    from app.infra.sftp_watcher import SFTPWatcher

    log.info("sftp-ingest starting")

    blob  = get_blob_storage()   # reads MINIO_ENDPOINT from env; creds from Vault
    queue = get_classify_queue() # reads REDIS_URL from env

    watcher = SFTPWatcher(
        host          = os.environ.get("SFTP_HOST",           "sftp"),
        port          = int(os.environ.get("SFTP_PORT",       "22")),
        user          = os.environ.get("SFTP_USER",           "scanner"),
        password      = os.environ.get("SFTP_PASSWORD",       "scanner"),
        watch_path    = os.environ.get("SFTP_WATCH_PATH",     "/upload"),
        poll_interval = int(os.environ.get("SFTP_POLL_INTERVAL", "5")),
        blob          = blob,
        queue         = queue,
        create_batch  = _create_batch,
    )

    log.info(
        "SFTPWatcher configured host=%s path=%s interval=%ss",
        os.environ.get("SFTP_HOST", "sftp"),
        os.environ.get("SFTP_WATCH_PATH", "/upload"),
        os.environ.get("SFTP_POLL_INTERVAL", "5"),
    )
    await watcher.run()  # runs forever; exceptions within a cycle are caught internally


if __name__ == "__main__":
    asyncio.run(_main())
