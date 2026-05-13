"""
Domain model for a document prediction.

One prediction row is written per document after the inference worker
finishes.  Reviewers can relabel predictions where confidence < 0.7.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.classifier.classes import CLASSES


class Prediction(BaseModel):
    id:              str
    batch_id:        str
    filename:        str
    blob_key:        str    # minio://documents/batches/.../original/doc.tiff
    overlay_key:     str    # minio://documents/batches/.../overlay/doc.png
    predicted_class: str
    confidence:      float
    relabeled_class: str | None = None  # set by reviewer; None until relabeled
    created_at:      datetime

    model_config = {"from_attributes": True}


class PredictionCreate(BaseModel):
    """Input shape used by PredictionRepository.create()."""
    batch_id:        str
    filename:        str
    blob_key:        str
    overlay_key:     str
    predicted_class: str
    confidence:      float


class PredictionRelabel(BaseModel):
    """Input shape for the reviewer relabel endpoint."""
    relabeled_class: str

    @field_validator("relabeled_class")
    @classmethod
    def must_be_valid_class(cls, v: str) -> str:
        # Validated automatically on model creation — no need to call manually.
        if v not in CLASSES:
            raise ValueError(
                f"'{v}' is not a valid class. Choose from: {CLASSES}"
            )
        return v
