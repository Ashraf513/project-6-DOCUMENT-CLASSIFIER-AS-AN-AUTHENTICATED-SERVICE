# Location: app/repositories/prediction_repo.py
# Fixed – no internal commits; service handles transaction.

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Prediction as PredictionORM
from app.domain.prediction import Prediction, PredictionCreate, PredictionRelabel


class PredictionRepo:
    """Repository for Prediction operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, batch_id: str, pred_create: PredictionCreate
    ) -> Prediction:
        """Create a new prediction (does NOT commit)."""
        now = datetime.now(timezone.utc)
        pred_orm = PredictionORM(
            id=str(uuid.uuid4()),
            batch_id=batch_id,
            filename=pred_create.filename,
            blob_key=pred_create.blob_key,
            overlay_key=pred_create.overlay_key,
            predicted_class=pred_create.predicted_class,
            confidence=pred_create.confidence,
            created_at=now,
        )
        self.session.add(pred_orm)
        # No commit
        return Prediction.model_validate(pred_orm)

    async def get_by_id(self, prediction_id: str) -> Optional[Prediction]:
        result = await self.session.execute(
            select(PredictionORM).where(PredictionORM.id == prediction_id)
        )
        pred_orm = result.scalar_one_or_none()
        return Prediction.model_validate(pred_orm) if pred_orm else None

    async def get_by_batch_id(self, batch_id: str) -> List[Prediction]:
        result = await self.session.execute(
            select(PredictionORM)
            .where(PredictionORM.batch_id == batch_id)
            .order_by(PredictionORM.created_at.desc())
        )
        pred_orms = result.scalars().all()
        return [Prediction.model_validate(p) for p in pred_orms]

    async def get_recent(self, limit: int = 50) -> List[Prediction]:
        result = await self.session.execute(
            select(PredictionORM)
            .order_by(PredictionORM.created_at.desc())
            .limit(limit)
        )
        pred_orms = result.scalars().all()
        return [Prediction.model_validate(p) for p in pred_orms]

    async def get_by_batch_and_filename(
        self, batch_id: str, filename: str
    ) -> Optional[Prediction]:
        result = await self.session.execute(
            select(PredictionORM).where(
                (PredictionORM.batch_id == batch_id)
                & (PredictionORM.filename == filename)
            )
        )
        pred_orm = result.scalar_one_or_none()
        return Prediction.model_validate(pred_orm) if pred_orm else None

    async def relabel(
        self, prediction_id: str, relabel_model: PredictionRelabel
    ) -> Optional[Prediction]:
        """Update relabeled_class (does NOT commit)."""
        stmt = (
            update(PredictionORM)
            .where(PredictionORM.id == prediction_id)
            .values(relabeled_class=relabel_model.relabeled_class)
            .returning(PredictionORM)
        )
        result = await self.session.execute(stmt)
        pred_orm = result.scalar_one_or_none()
        # No commit
        return Prediction.model_validate(pred_orm) if pred_orm else None

    async def list_by_predicted_class(
        self, cls: str, limit: int = 100, offset: int = 0
    ) -> List[Prediction]:
        result = await self.session.execute(
            select(PredictionORM)
            .where(PredictionORM.predicted_class == cls)
            .offset(offset)
            .limit(limit)
            .order_by(PredictionORM.created_at.desc())
        )
        pred_orms = result.scalars().all()
        return [Prediction.model_validate(p) for p in pred_orms]

    async def list_unrelabeled(
        self, limit: int = 100, offset: int = 0
    ) -> List[Prediction]:
        result = await self.session.execute(
            select(PredictionORM)
            .where(PredictionORM.relabeled_class.is_(None))
            .offset(offset)
            .limit(limit)
            .order_by(PredictionORM.created_at.desc())
        )
        pred_orms = result.scalars().all()
        return [Prediction.model_validate(p) for p in pred_orms]