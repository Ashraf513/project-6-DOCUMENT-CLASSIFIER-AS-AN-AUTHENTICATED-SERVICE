# Location: app/services/batch_service.py
# Business logic: batch management and lifecycle.
# Transitions are audited and cache is invalidated after each write.

from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.batch import Batch, BatchStatus, BatchCreate
from app.domain.user import User
from app.repositories.batch_repo import BatchRepo
from app.repositories.audit_repo import AuditRepo
from app.infra.cache import (
    CacheInvalidator,
    BATCHES_LIST_KEY,
    batch_key,
)
from app.services.exceptions import (
    NotFound,
    InvalidStateTransition,
)


class BatchService:
    """
    Manages document batches and their lifecycle.
    Valid status transitions:
        pending → processing, failed
        processing → done, failed
        done → (terminal), failed → (terminal, but may be re‑queued)
    """

    def __init__(self, db: AsyncSession, cache: CacheInvalidator):
        self.db = db
        self.cache = cache
        self.batch_repo = BatchRepo(db)
        self.audit_repo = AuditRepo(db)

    async def create_batch(
        self,
        data: BatchCreate | None = None,
        actor: User | None = None,
    ) -> Batch:
        if data is None:
            data = BatchCreate()

        async with self.db.begin():
            batch = await self.batch_repo.create(data)
            await self.audit_repo.create(
                actor_id=actor.id if actor else None,
                action="batch_created",
                target=f"batch:{batch.id}",
                details={"file_count": data.file_count},
            )

        await self.cache.delete(BATCHES_LIST_KEY)
        return batch

    async def get_batch(self, batch_id: str) -> Batch:
        async with self.db.begin():
            batch = await self.batch_repo.get_by_id(batch_id)
            if not batch:
                raise NotFound("Batch not found")
            return batch

    async def list_batches(self, skip: int = 0, limit: int = 20) -> list[Batch]:
        async with self.db.begin():
            return await self.batch_repo.list(limit=limit, offset=skip)

    async def _transition(
        self, batch_id: str, new_status: BatchStatus, allowed: set[BatchStatus]
    ) -> Batch:
        async with self.db.begin():
            batch = await self.batch_repo.get_by_id(batch_id)
            if not batch:
                raise NotFound("Batch not found")

            if batch.status not in allowed:
                raise InvalidStateTransition(
                    f"Cannot move from '{batch.status.value}' to '{new_status.value}'"
                )

            updated = await self.batch_repo.update_status(batch_id, new_status)
            if not updated:
                raise NotFound("Batch not found after update")

            await self.audit_repo.create(
                actor_id=None,
                action="batch_state_change",
                target=f"batch:{batch_id}",
                details={
                    "from": batch.status.value,
                    "to": new_status.value,
                },
            )

        await self.cache.delete(batch_key(batch_id))
        await self.cache.delete(BATCHES_LIST_KEY)
        return updated

    async def mark_processing(self, batch_id: str) -> Batch:
        return await self._transition(
            batch_id,
            BatchStatus.processing,
            allowed={BatchStatus.pending},
        )

    async def mark_done(self, batch_id: str) -> Batch:
        return await self._transition(
            batch_id,
            BatchStatus.done,
            allowed={BatchStatus.processing},
        )

    async def mark_failed(self, batch_id: str) -> Batch:
        return await self._transition(
            batch_id,
            BatchStatus.failed,
            allowed={BatchStatus.pending, BatchStatus.processing},
        )