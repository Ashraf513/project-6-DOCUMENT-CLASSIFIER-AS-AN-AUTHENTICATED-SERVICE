# Phase 8: Workers — Background Job Processing

## What Is This Phase?

Workers are **background processes** that run separately from the API. They handle the heavy, slow, or asynchronous work:
- The **sftp-ingest worker** watches the SFTP server for new files.
- The **inference worker** picks up queued jobs and runs the AI classifier.

Neither worker handles HTTP requests — they communicate through Redis (the job queue) and the database.

---

## The Two Workers

```
[SFTP Server]
     |
     | new TIFF dropped
     v
[sftp-ingest worker]         ← container: sftp-ingest
     |    |
     |    | 1. uploads file to MinIO
     |    | 2. creates batch in DB
     |    | 3. enqueues job in Redis
     v    v
   MinIO  Redis queue
              |
              | job dequeued
              v
[inference worker]           ← container: worker
     |    |
     |    | 1. downloads file from MinIO
     |    | 2. runs AI classifier
     |    | 3. writes prediction to DB
     |    | 4. writes overlay PNG to MinIO
     |    | 5. invalidates Redis cache
     v    v
  Postgres  MinIO
```

---

## Files in This Directory

```
app/workers/
├── README.md            ← you are here
├── __init__.py
├── sftp_ingest.py       ← entry point for the sftp-ingest container
└── inference_worker.py  ← entry point for the worker container
```

---

## sftp_ingest.py — The SFTP Ingestion Worker

This file is the **entry point** for the `sftp-ingest` container. When the container starts, it runs this script, which runs forever in a polling loop.

```python
# sftp_ingest.py — simplified structure

import asyncio
from app.infra.sftp_watcher import SFTPWatcher
from app.infra.blob import BlobClient
from app.infra.vault import VaultClient
from app.infra.queue import get_queue

async def main():
    # 1. Load all secrets from Vault
    vault      = VaultClient(os.environ["VAULT_ADDR"], os.environ["VAULT_TOKEN"])
    blob       = BlobClient(...)
    queue      = get_queue(vault.get_secret("redis", "url"))

    # 2. Start the watcher loop
    watcher = SFTPWatcher(
        sftp_host=vault.get_secret("sftp", "host"),
        sftp_user=vault.get_secret("sftp", "user"),
        sftp_password=vault.get_secret("sftp", "password"),
        sftp_path="/upload",
        blob_client=blob,
        queue=queue,
    )
    await watcher.run()  # runs forever, polling every 2 seconds

if __name__ == "__main__":
    asyncio.run(main())
```

**What the ingest worker does per file:**
1. Detects a new TIFF on SFTP.
2. Validates it (not zero-byte, not too large, is a TIFF).
3. Downloads it from SFTP.
4. Uploads it to MinIO (`batches/{batch_id}/original/{filename}.tiff`).
5. Creates a new batch record in the database (status: `pending`).
6. Enqueues a job: `{"batch_id": "...", "blob_key": "..."}`.
7. Marks the file as "seen" so it is not processed again.

---

## inference_worker.py — The Inference Worker

This file is the **entry point** for the `worker` container. RQ (Redis Queue) manages the job queue — you run `rq worker` and it picks up jobs automatically.

```python
# inference_worker.py — the classify function that RQ calls

import structlog
from app.classifier.model import load_model, predict
from app.classifier.overlay import draw_overlay
from app.infra.blob import BlobClient
from app.services.prediction_service import PredictionService

log = structlog.get_logger()

def classify(batch_id: str, blob_key: str, request_id: str):
    """
    This function is called by RQ when a job is dequeued.
    It must be importable at module level (RQ requirement).
    """
    log = log.bind(batch_id=batch_id, blob_key=blob_key, request_id=request_id)
    log.info("job_started")

    try:
        # 1. Load model (cached — only loaded once per worker process)
        model = load_model()

        # 2. Download the document from MinIO
        image_bytes = blob.download(blob_key)
        log.info("file_downloaded", size_bytes=len(image_bytes))

        # 3. Run inference
        predicted_class, confidence, all_scores = predict(model, image_bytes)
        log.info("inference_done",
                 predicted_class=predicted_class,
                 confidence=confidence)

        # 4. Draw the overlay PNG (annotated result image)
        overlay_bytes = draw_overlay(image_bytes, predicted_class, confidence)

        # 5. Upload overlay to MinIO
        overlay_key = blob_key.replace("original/", "overlay/").replace(".tiff", ".png")
        blob.upload(overlay_key, overlay_bytes, "image/png")

        # 6. Write prediction to database
        prediction_service.save_prediction(
            batch_id=batch_id,
            filename=os.path.basename(blob_key),
            blob_key=blob_key,
            overlay_key=overlay_key,
            predicted_class=predicted_class,
            confidence=confidence,
        )

        # 7. Invalidate relevant caches
        # (done inside prediction_service.save_prediction via the service layer)

        log.info("job_completed", predicted_class=predicted_class)

    except MinIOUnavailableError:
        log.error("minio_unreachable", blob_key=blob_key)
        raise  # RQ will move this to the failed queue for retry

    except Exception as e:
        log.error("job_failed", error=str(e))
        raise
```

---

## How RQ (Redis Queue) Works

RQ is a simple job queue backed by Redis.

```
Producer (sftp-ingest worker):          Consumer (inference worker):
queue.enqueue("classify",               rq worker --url redis://redis:6379
    batch_id="...",                               ↓
    blob_key="...")                      picks up "classify" job
         |                                        ↓
         | stores job in Redis                calls classify(batch_id, blob_key)
         v                                        ↓
     Redis queue                          job succeeds → removed from queue
                                          job fails → moved to failed queue
```

**RQ queues:**
| Queue | Purpose |
|-------|---------|
| `default` | Normal classification jobs |
| `failed` | Jobs that raised an exception — can be retried manually |

**Starting the RQ worker (inside the container):**
```bash
rq worker --url redis://redis:6379 default
```

---

## The Request ID — Tracing Across Services

Every job carries a `request_id` (a UUID generated when the file is first detected on SFTP). This ID is passed through the queue, into the inference worker, and included in all log lines.

This means you can trace a single document's journey across all services:

```
sftp-ingest: {"event": "file_detected", "request_id": "abc-123", "filename": "doc.tiff"}
sftp-ingest: {"event": "job_enqueued",  "request_id": "abc-123", "blob_key": "..."}
worker:      {"event": "job_started",   "request_id": "abc-123", "batch_id": "..."}
worker:      {"event": "inference_done","request_id": "abc-123", "predicted_class": "invoice"}
worker:      {"event": "job_completed", "request_id": "abc-123"}
```

In the API, the same `request_id` is included in HTTP response headers so you can correlate API requests with worker jobs.

---

## Structured Logging

All log output is **JSON format** (not plain text). This allows log aggregation tools (like Elasticsearch or CloudWatch) to parse and search logs.

```json
{
  "timestamp": "2026-05-12T10:00:01Z",
  "level": "info",
  "event": "inference_done",
  "request_id": "abc-123-def",
  "batch_id": "batch-456",
  "predicted_class": "invoice",
  "confidence": 0.87,
  "duration_ms": 423
}
```

We use the `structlog` library which makes this easy:
```python
log = structlog.get_logger()
log.info("inference_done", predicted_class=predicted_class, confidence=confidence)
```

---

## Error Handling and Recovery

| Scenario | What Happens |
|----------|-------------|
| MinIO unreachable mid-job | Exception raised → RQ moves job to failed queue → ops team retries manually |
| Redis container restarted (queue lost) | RQ's failed jobs are stored in Redis — if Redis is empty, in-flight jobs are lost. Recovery: re-ingest by re-dropping the TIFF files into SFTP |
| Malformed image (not a real TIFF) | `PIL.Image.open()` raises an exception → job fails → logged with filename for investigation |
| Model weights missing at startup | Worker refuses to start — startup check in `load_model()` raises immediately |
| SHA-256 mismatch | Worker refuses to start — integrity check fails |

---

## Startup Checks (Worker Refuses to Start If...)

Before the worker starts accepting jobs, it runs:
```python
def load_model():
    model_card = json.load(open("app/classifier/models/model_card.json"))

    # Check 1: weights file exists
    weights_path = Path("app/classifier/models/classifier.pt")
    if not weights_path.exists():
        raise RuntimeError("Classifier weights not found — cannot start worker")

    # Check 2: SHA-256 matches model card
    actual_hash = sha256(weights_path.read_bytes()).hexdigest()
    if actual_hash != model_card["sha256"]:
        raise RuntimeError(f"SHA-256 mismatch — weights may be corrupted")

    # Check 3: model card's test accuracy meets the threshold from README
    if model_card["test_top1"] < MINIMUM_ACCURACY_THRESHOLD:
        raise RuntimeError(f"Model accuracy {model_card['test_top1']} is below threshold")

    model = load_convnext(model_card["backbone"])
    model.load_state_dict(torch.load(weights_path, map_location="cpu"))
    model.eval()
    return model
```

---

## Performance Target

- Inference per document (p95): **< 1.0 second** (CPU, ConvNeXt Tiny or Small)
- End-to-end — SFTP drop → visible in API (p95): **< 10 seconds**
  - 2s polling interval + upload + queue + inference + DB write = well under 10s on local hardware

---

## What You Need to Know for the Presentation

- What is a job queue and why use Redis for it?
  - Answer: a queue decouples the ingest step from the inference step; Redis provides fast, persistent storage for pending jobs
- What happens when the inference worker crashes mid-job?
  - Answer: RQ marks the job as failed; the file stays in MinIO; the job can be retried from the failed queue
- Why is the model loaded once at worker startup rather than per job?
  - Answer: loading a model from disk takes ~1 second; loading per job would make inference extremely slow
- What is `request_id` and why pass it through the queue?
  - Answer: allows you to correlate all log lines for a single document across multiple services — essential for debugging
- Why does the worker refuse to start if SHA-256 doesn't match?
  - Answer: prevents silently running the wrong model — catches accidental overwrites or corrupted downloads
