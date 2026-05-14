"""
RQ (Redis Queue) job dispatch helper.

The inference worker function is referenced by its importable dotted path:
    app.workers.inference_worker.classify

RQ resolves this at dequeue time — the worker container must have the
full app package on its PYTHONPATH (it does; see Dockerfile worker stage).

Queues:
    default  — normal classification jobs (what we enqueue here)
    failed   — RQ's built-in dead-letter queue for jobs that raised exceptions

The ClassifyQueue wraps a single rq.Queue instance.  One ClassifyQueue
instance lives for the lifetime of the sftp-ingest process.
"""

from __future__ import annotations

import os

import redis
from rq import Queue
from rq.job import Job


QUEUE_NAME   = "default"
JOB_TIMEOUT  = 120   # seconds — inference must complete within 2 min
RESULT_TTL   = 86_400  # keep successful job results for 24 h
FAILURE_TTL  = 7 * 86_400  # keep failed job results for 7 days


class ClassifyQueue:
    """Thin wrapper around an RQ Queue for enqueuing document-classify jobs."""

    def __init__(self, redis_url: str) -> None:
        conn = redis.from_url(redis_url)
        self._queue = Queue(
            name=QUEUE_NAME,
            connection=conn,
            default_timeout=JOB_TIMEOUT,
        )

    def enqueue_classify(
        self,
        batch_id: str,
        blob_key: str,
        request_id: str,
    ) -> str:
        """
        Enqueue a classification job and return the RQ job ID.

        The inference worker will call:
            app.workers.inference_worker.classify(
                batch_id=batch_id,
                blob_key=blob_key,
                request_id=request_id,
            )
        """
        job: Job = self._queue.enqueue(
            "app.workers.inference_worker.classify",
            kwargs={
                "batch_id":   batch_id,
                "blob_key":   blob_key,
                "request_id": request_id,
            },
            result_ttl=RESULT_TTL,
            failure_ttl=FAILURE_TTL,
            job_timeout=JOB_TIMEOUT,
        )
        return job.id

    @property
    def depth(self) -> int:
        """Number of jobs currently waiting in the queue."""
        return len(self._queue)


# ── Factory ──────────────────────────────────────────────────────────────────

def get_classify_queue() -> ClassifyQueue:
    """
    Build a ClassifyQueue from the REDIS_URL environment variable.
    Call once at process startup and reuse the instance.
    """
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return ClassifyQueue(redis_url)