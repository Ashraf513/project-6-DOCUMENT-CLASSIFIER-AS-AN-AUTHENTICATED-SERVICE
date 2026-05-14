"""
RQ inference worker — classify() is called by RQ when a job is dequeued.

The function is registered in Redis by its importable dotted path:
    "app.workers.inference_worker.classify"

Start the worker container with:
    rq worker --with-scheduler default

Job flow:
    1. Download document bytes from MinIO.
    2. Run inference via the ConvNeXt-Tiny classifier.
    3. Draw annotated overlay PNG and upload it back to MinIO.
    4. Persist via the service layer:
         BatchService.mark_processing() → mark_done()
         PredictionService.save_prediction()
       The service layer owns transaction boundaries AND cache invalidation —
       the worker never touches the ORM or Redis directly.
    5. Return a result dict — RQ stores it in Redis for inspection.

Process-level singletons (_blob, _model) are initialised on the first job
and reused across all subsequent jobs in the same worker process.  Loading a
ConvNeXt-Tiny from disk takes ~2 s on CPU — doing it per-job would destroy
throughput.

Async services in a sync worker:
    RQ workers are synchronous.  Services use AsyncSession.  The solution is
    asyncio.run() inside _persist() — each job gets its own short-lived event
    loop just for the DB/cache work.
"""
from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)

# ── process-level singletons ──────────────────────────────────────────────────

_blob  = None
_model = None


def _get_blob():
    global _blob
    if _blob is None:
        from app.infra.blob import get_blob_storage
        _blob = get_blob_storage()  # reads MINIO_ENDPOINT from env; creds from Vault
    return _blob


def _get_model():
    global _model
    if _model is None:
        from app.classifier.model import load_model
        _model = load_model()  # raises if weights missing or SHA-256 mismatch
    return _model


# ── RQ job function ───────────────────────────────────────────────────────────

def classify(batch_id: str, blob_key: str, request_id: str) -> dict:
    """
    Entry point called by RQ.  Must remain importable at module level.

    Returns:
        {
            "label":       "invoice",
            "confidence":  0.92,
            "batch_id":    "...",
            "blob_key":    "batches/.../original/doc.tiff",
            "overlay_key": "batches/.../overlay/doc.png",
        }

    Raises on any unrecoverable error — RQ moves the job to the failed queue.
    """
    log.info(
        "job_started batch_id=%s blob_key=%s request_id=%s",
        batch_id, blob_key, request_id,
    )

    from app.classifier.model import predict
    from app.classifier.overlay import draw_overlay
    from app.infra.blob import BlobStorage

    blob  = _get_blob()
    model = _get_model()

    # 1 ── download ─────────────────────────────────────────────────────────────
    image_bytes = blob.download(blob_key)
    log.info("file_downloaded size_bytes=%d", len(image_bytes))

    # 2 ── inference ────────────────────────────────────────────────────────────
    label, confidence, _ = predict(model, image_bytes)
    log.info("inference_done label=%s confidence=%.4f", label, confidence)

    # 3 ── overlay ──────────────────────────────────────────────────────────────
    filename      = blob_key.rsplit("/", 1)[-1]
    overlay_key   = BlobStorage.overlay_key(batch_id, filename)
    overlay_bytes = draw_overlay(image_bytes, label, confidence)
    blob.upload(overlay_key, overlay_bytes, "image/png")
    log.info("overlay_uploaded key=%s", overlay_key)

    # 4 ── persist ──────────────────────────────────────────────────────────────
    _persist(
        batch_id    = batch_id,
        blob_key    = blob_key,
        overlay_key = overlay_key,
        filename    = filename,
        label       = label,
        confidence  = confidence,
        request_id  = request_id,
    )

    result = {
        "label":       label,
        "confidence":  confidence,
        "batch_id":    batch_id,
        "blob_key":    blob_key,
        "overlay_key": overlay_key,
    }
    log.info("job_completed batch_id=%s label=%s confidence=%.4f", batch_id, label, confidence)
    return result


# ── DB + cache persistence (via service layer) ────────────────────────────────

def _persist(
    *,
    batch_id:    str,
    blob_key:    str,
    overlay_key: str,
    filename:    str,
    label:       str,
    confidence:  float,
    request_id:  str,
) -> None:
    """
    Delegate all DB writes and cache invalidation to the service layer.

    asyncio.run() bridges the sync RQ context to the async services.
    Each call gets its own short-lived event loop — safe because RQ
    processes one job at a time per worker process.
    """
    asyncio.run(
        _persist_async(
            batch_id    = batch_id,
            blob_key    = blob_key,
            overlay_key = overlay_key,
            filename    = filename,
            label       = label,
            confidence  = confidence,
            request_id  = request_id,
        )
    )
    log.info("db_persisted batch_id=%s", batch_id)


async def _persist_async(
    *,
    batch_id:    str,
    blob_key:    str,
    overlay_key: str,
    filename:    str,
    label:       str,
    confidence:  float,
    request_id:  str,
) -> None:
    """
    Async implementation of the persistence step.

    Uses BatchService and PredictionService so that:
    - Transaction boundaries are owned by the service layer (not the worker).
    - Cache keys (batch:{id}, predictions:recent, etc.) are invalidated here,
      meaning GET /batches/{id} returns fresh data immediately after the job.
    - AuditLog entries are written by the service layer as designed.

    Status transitions for multi-file batches:
        pending → processing  (mark_processing — first job wins, others silently skip)
        processing → done     (mark_done — last job wins, earlier ones silently skip)
    InvalidStateTransition is caught and logged, not re-raised, because a
    sibling job in the same batch may have already advanced the status.
    """
    from app.db.session import AsyncSessionLocal
    from app.infra.cache import RedisCacheInvalidator
    from app.services.batch_service import BatchService
    from app.services.prediction_service import PredictionService
    from app.services.exceptions import InvalidStateTransition
    from app.domain.prediction import PredictionCreate

    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    cache     = RedisCacheInvalidator(redis_url)

    try:
        async with AsyncSessionLocal() as session:
            batch_svc = BatchService(session, cache)
            pred_svc  = PredictionService(session, cache)

            # pending → processing (idempotent for multi-file batches)
            try:
                await batch_svc.mark_processing(batch_id)
            except InvalidStateTransition:
                log.debug("batch %s already past pending — skipping mark_processing", batch_id)

            # Save prediction row + invalidate cache keys
            await pred_svc.save_prediction(
                batch_id = batch_id,
                data     = PredictionCreate(
                    batch_id        = batch_id,
                    filename        = filename,
                    blob_key        = blob_key,
                    overlay_key     = overlay_key,
                    predicted_class = label,
                    confidence      = confidence,
                ),
            )

            # processing → done (idempotent for multi-file batches)
            try:
                await batch_svc.mark_done(batch_id)
            except InvalidStateTransition:
                log.debug("batch %s already past processing — skipping mark_done", batch_id)

    finally:
        await cache.close()
