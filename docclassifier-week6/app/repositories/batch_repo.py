# Location: app/repositories/batch_repo.py
# Fixed – no internal commits; service handles transaction.

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Batch as BatchORM
from app.domain.batch import Batch, BatchCreate, BatchStatus


class BatchRepo:
    """Repository for Batch operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, batch_create: BatchCreate) -> Batch:
        """Create a new batch (does NOT commit)."""
        from datetime import datetime, timezone
        batch_orm = BatchORM(
            id=batch_create.id,
            file_count=batch_create.file_count,
            status=BatchStatus.pending,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(batch_orm)
        return Batch.model_validate(batch_orm)

    async def get_by_id(self, batch_id: str) -> Optional[Batch]:
        result = await self.session.execute(
            select(BatchORM).where(BatchORM.id == batch_id)
        )
        batch_orm = result.scalar_one_or_none()
        return Batch.model_validate(batch_orm) if batch_orm else None

    async def list(self, limit: int = 100, offset: int = 0) -> List[Batch]:
        result = await self.session.execute(
            select(BatchORM)
            .offset(offset)
            .limit(limit)
            .order_by(BatchORM.created_at.desc())
        )
        batch_orms = result.scalars().all()
        return [Batch.model_validate(b) for b in batch_orms]

    async def list_by_status(
        self, status: BatchStatus, limit: int = 100, offset: int = 0
    ) -> List[Batch]:
        result = await self.session.execute(
            select(BatchORM)
            .where(BatchORM.status == status)
            .offset(offset)
            .limit(limit)
            .order_by(BatchORM.created_at.desc())
        )
        batch_orms = result.scalars().all()
        return [Batch.model_validate(b) for b in batch_orms]

    async def update_status(
        self, batch_id: str, new_status: BatchStatus
    ) -> Optional[Batch]:
        """Update batch status (does NOT commit)."""
        stmt = (
            update(BatchORM)
            .where(BatchORM.id == batch_id)
            .values(status=new_status)
            .returning(BatchORM)
        )
        result = await self.session.execute(stmt)
        batch_orm = result.scalar_one_or_none()
        # No commit
        return Batch.model_validate(batch_orm) if batch_orm else None

    async def increment_file_count(
        self, batch_id: str, count: int = 1
    ) -> Optional[Batch]:
        """Increment file count (does NOT commit)."""
        batch = await self.get_by_id(batch_id)
        if not batch:
            return None
        stmt = (
            update(BatchORM)
            .where(BatchORM.id == batch_id)
            .values(file_count=BatchORM.file_count + count)
            .returning(BatchORM)
        )
        result = await self.session.execute(stmt)
        batch_orm = result.scalar_one_or_none()
        return Batch.model_validate(batch_orm) if batch_orm else None