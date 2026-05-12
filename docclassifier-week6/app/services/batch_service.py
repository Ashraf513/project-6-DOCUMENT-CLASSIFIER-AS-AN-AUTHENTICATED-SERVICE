# Location: app/services/batch_service.py
# Main purpose: Business logic for batch management.
# This service handles batch creation, status transitions (pending → processing → done),
# listing, and retrieval. It ensures state changes are audited and cache is invalidated.

from uuid import UUID
from app.domain.batch import Batch, BatchDetail
from app.domain.user import User


class BatchService:
    """
    Manages document batches and their lifecycle.
    """

    def __init__(self, batch_repo, audit_repo, cache):
        """
        Inject dependencies.
        :param batch_repo: BatchRepository instance
        :param audit_repo: AuditRepository instance
        :param cache: CacheInvalidator instance
        """
        self.batch_repo = batch_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def create_batch(self, actor: User | None = None) -> Batch:
        """
        Create a new batch in 'pending' state.
        Called by the SFTP ingest worker (or admin).
        :param actor: optional user who initiated creation (or None for system)
        :return: newly created Batch domain model (summary)
        """
        # Phase 1 stub – returns a dummy batch with typical fields
        return Batch(
            id=UUID("10000000-0000-0000-0000-000000000000"),
            status="pending",
            created_at="2025-01-01T00:00:00Z",
            prediction_count=0
        )

    async def get_batch(self, batch_id: UUID) -> BatchDetail:
        """
        Retrieve a single batch including its predictions.
        :param batch_id: UUID of the batch
        :return: BatchDetail domain model (extended summary with predictions list)
        """
        # Phase 1 stub – returns a BatchDetail with empty prediction list
        return BatchDetail(
            id=batch_id,
            status="processing",
            created_at="2025-01-01T00:00:00Z",
            prediction_count=3,
            predictions=[]
        )

    async def list_batches(self, skip: int = 0, limit: int = 20) -> list[Batch]:
        """
        Return a paginated list of batch summaries.
        :param skip: number of items to skip (offset)
        :param limit: maximum number of items to return
        :return: list of Batch domain models (summary)
        """
        # Phase 1 stub – two dummy batches
        return [
            Batch(id=UUID("10000000-0000-0000-0000-000000000001"),
                  status="done", created_at="2025-01-01T00:00:00Z", prediction_count=5),
            Batch(id=UUID("10000000-0000-0000-0000-000000000002"),
                  status="processing", created_at="2025-01-02T00:00:00Z", prediction_count=2),
        ]

    async def mark_processing(self, batch_id: UUID) -> Batch:
        """
        Transition a batch to 'processing' state.
        Typically called once the first document is picked up for inference.
        :param batch_id: UUID of the batch
        :return: updated Batch domain model
        """
        # Phase 1 stub – returns a batch with status "processing"
        return Batch(id=batch_id, status="processing",
                     created_at="2025-01-01T00:00:00Z", prediction_count=0)

    async def mark_done(self, batch_id: UUID) -> Batch:
        """
        Transition a batch to 'done' state.
        Called after all documents in the batch have been classified.
        :param batch_id: UUID of the batch
        :return: updated Batch domain model
        """
        # Phase 1 stub – returns a batch with status "done"
        return Batch(id=batch_id, status="done",
                     created_at="2025-01-01T00:00:00Z", prediction_count=10)