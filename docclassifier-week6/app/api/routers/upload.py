"""
HTTP file upload endpoint — alternative ingestion path to SFTP.

POST /upload/
  Accepts one or more TIFF files as multipart/form-data.
  Validates each file, uploads originals to MinIO, creates a Batch,
  and enqueues a classify job per file.  Returns the batch_id so the
  caller can poll GET /batches/{batch_id} for status.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import List

import casbin
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_batch_service, get_enforcer
from app.api.routers.auth import current_domain_user
from app.domain.batch import BatchCreate
from app.domain.user import User
from app.infra.blob import BlobStorage, get_blob_storage
from app.infra.queue import ClassifyQueue, get_classify_queue
from app.services.batch_service import BatchService

router = APIRouter(prefix="/upload", tags=["upload"])

VALID_EXTENSIONS = frozenset({".tiff", ".tif"})
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB hard cap

# Process-level singletons — created on first upload request, reused after.
_blob: BlobStorage | None = None
_queue: ClassifyQueue | None = None


def _get_blob() -> BlobStorage:
    global _blob
    if _blob is None:
        _blob = get_blob_storage()
    return _blob


def _get_queue() -> ClassifyQueue:
    global _queue
    if _queue is None:
        _queue = get_classify_queue()
    return _queue


@router.post("/")
async def upload_documents(
    files: List[UploadFile] = File(..., description="One or more TIFF files to classify"),
    actor: User = Depends(current_domain_user),
    batch_svc: BatchService = Depends(get_batch_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    """
    Upload TIFF documents for classification.

    - Creates one Batch covering all uploaded files.
    - Enqueues one classify job per file.
    - Returns batch_id to poll for results.
    """
    if not enforcer.enforce(actor.role.value, "/upload", "POST"):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not files:
        raise HTTPException(status_code=422, detail="No files provided.")

    # Validate extensions before reading any content
    for f in files:
        name = f.filename or ""
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext not in VALID_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"'{name}': only .tiff and .tif files are accepted.",
            )

    # Read all content up front so we can validate sizes before touching MinIO
    file_data: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        if not content:
            raise HTTPException(status_code=422, detail=f"'{f.filename}' is empty.")
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"'{f.filename}' exceeds the 100 MB size limit.",
            )
        file_data.append((f.filename or f"upload_{uuid.uuid4()}.tiff", content))

    # Create batch record before touching MinIO so the audit log is consistent
    batch = await batch_svc.create_batch(
        data=BatchCreate(file_count=len(file_data)),
        actor=actor,
    )
    batch_id = batch.id
    request_id = str(uuid.uuid4())

    blob = _get_blob()
    queue = _get_queue()

    jobs: list[dict] = []
    for filename, content in file_data:
        blob_key = BlobStorage.original_key(batch_id, filename)
        await asyncio.to_thread(blob.upload, blob_key, content, "image/tiff")
        job_id = await asyncio.to_thread(
            queue.enqueue_classify, batch_id, blob_key, request_id
        )
        jobs.append({"filename": filename, "blob_key": blob_key, "job_id": job_id})

    return {
        "batch_id": batch_id,
        "file_count": len(file_data),
        "request_id": request_id,
        "jobs": jobs,
    }
