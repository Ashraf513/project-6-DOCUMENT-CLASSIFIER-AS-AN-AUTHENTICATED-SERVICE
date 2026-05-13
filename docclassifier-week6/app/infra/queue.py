"""
Queue adapter — wraps Redis + RQ.

Public interface:
    get_queue(redis_url)                              -> rq.Queue
    enqueue_job(queue, batch_id, blob_key, request_id) -> rq.job.Job

The job function path "app.workers.inference_worker.classify" is the
string RQ stores in Redis and imports when a worker picks up the job.
Workers must be started with:
    rq worker --url redis://redis:6379 default
"""

import redis as redis_lib
import structlog
from rq import Queue
from rq.job import Job

log = structlog.get_logger()

QUEUE_NAME = "default"
JOB_TIMEOUT = 120   # seconds — prevents a hung job from blocking the queue forever
RESULT_TTL  = 3600  # keep result in Redis for 1 hour, then auto-delete to avoid memory bloat


def get_redis(redis_url: str) -> redis_lib.Redis:
    """Connect to Redis; fail fast if unreachable."""
    conn = redis_lib.from_url(redis_url, decode_responses=False)
    conn.ping()
    log.info("redis_connected", url=redis_url)
    return conn


def get_queue(redis_url: str) -> Queue:
    """Return a configured RQ Queue using the default queue name."""
    conn = get_redis(redis_url)
    return Queue(QUEUE_NAME, connection=conn)


def enqueue_job(
    queue: Queue,
    batch_id: str,
    blob_key: str,
    request_id: str,
) -> Job:
    """Enqueue a classify job; returns the RQ Job object."""
    # Pass the function as a string, not a reference.  RQ stores this string
    # in Redis and the *worker* process imports it.  A direct reference would
    # bind the enqueuer's import path, which may differ from the worker's.
    job = queue.enqueue(
        "app.workers.inference_worker.classify",
        kwargs={
            "batch_id":   batch_id,
            "blob_key":   blob_key,
            "request_id": request_id,
        },
        job_timeout=JOB_TIMEOUT,
        result_ttl=RESULT_TTL,
    )
    log.info(
        "job_enqueued",
        job_id=job.id,
        batch_id=batch_id,
        blob_key=blob_key,
        request_id=request_id,
    )
    return job
