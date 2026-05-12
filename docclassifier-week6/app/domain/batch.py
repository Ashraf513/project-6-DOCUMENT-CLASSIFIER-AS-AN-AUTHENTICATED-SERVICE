# Location: app/domain/batch.py
# Purpose: Pydantic schemas for Batch summary and detail

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from .prediction import Prediction   # we'll create Prediction next

class Batch(BaseModel):
    """Batch summary (used in list responses)."""
    id: UUID
    status: str                     # "pending", "processing", "done"
    created_at: datetime
    prediction_count: int

    class Config:
        from_attributes = True

class BatchDetail(Batch):
    """Batch detail including its predictions."""
    predictions: list[Prediction] = []