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
    4. Persist Prediction + AuditLog rows to Postgres; mark Batch done.
    5. Return a result dict — RQ stores it in Redis for inspection.

Process-level singletons (_blob, _model) are initialised on the first job
and reused across all subsequent jobs in the same worker process.  Loading a
ConvNeXt-Tiny from disk takes ~2 s on CPU — doing it per-job would destroy
throughput.
"""
from __future__ import annotations

import logging
import uuid

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


# ── DB persistence ─────────────────────────────────────────────────────────────

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
    Write Prediction + AuditLog rows and mark the parent Batch as done.

    Uses the synchronous SQLAlchemy session (psycopg2) because RQ workers
    run in a plain synchronous execution context.
    """
    from app.db.session import SyncSessionLocal
    from app.db.models import Batch, Prediction, AuditLog
    from app.domain.batch import BatchStatus

    with SyncSessionLocal() as db:
        # Mark batch done (batch row was created by sftp-ingest's _create_batch)
        batch = db.get(Batch, batch_id)
        if batch is not None:
            batch.status = BatchStatus.done  # type: ignore[assignment]

        db.add(Prediction(
            id              = str(uuid.uuid4()),
            batch_id        = batch_id,
            filename        = filename,
            blob_key        = blob_key,
            overlay_key     = overlay_key,
            predicted_class = label,
            confidence      = confidence,
        ))

        db.add(AuditLog(
            id       = str(uuid.uuid4()),
            actor_id = None,  # system action — no human actor
            action   = "batch_state_change",
            target   = batch_id,
            details  = {
                "predicted_class": label,
                "confidence":      confidence,
                "request_id":      request_id,
            },
        ))

        db.commit()

    log.info("db_persisted batch_id=%s", batch_id)
