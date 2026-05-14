"""
Domain model for a document batch.

A batch is created when the SFTP watcher picks up one or more files in a
single poll cycle.  It groups those files under a shared ID and tracks their
processing state.

This is a Pydantic model — no SQLAlchemy, no HTTP.  Services pass these
objects around; the API serializes them to JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class BatchStatus(str, Enum):
    pending    = "pending"     # files uploaded to MinIO, jobs enqueued
    processing = "processing"  # at least one inference job running
    done       = "done"        # all jobs finished successfully
    failed     = "failed"      # at least one job failed permanently


class Batch(BaseModel):
    id:         str
    status:     BatchStatus
    file_count: int
    created_at: datetime

    # allows Batch.model_validate(orm_row) — ORM rows behave like dicts here
    model_config = {"from_attributes": True}


class BatchCreate(BaseModel):
    """Input shape used by BatchService.create()."""
    id:         str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_count: int = 0