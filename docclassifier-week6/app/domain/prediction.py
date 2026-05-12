# Location: app/domain/prediction.py
# Purpose: Pydantic schema for Prediction

from pydantic import BaseModel
from uuid import UUID

class Prediction(BaseModel):
    id: UUID
    batch_id: UUID
    filename: str
    blob_key: str
    overlay_key: str
    predicted_class: int
    confidence: float
    is_reviewed: bool = False

    class Config:
        from_attributes = True