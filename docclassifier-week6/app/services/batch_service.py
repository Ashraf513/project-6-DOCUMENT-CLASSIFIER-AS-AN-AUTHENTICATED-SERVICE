# Location: app/services/batch_service.py
# Main purpose: Business logic for batch management.
# This service handles batch creation, status transitions (pending -> processing -> done),
# listing, and retrieval. It ensures state changes are audited and cache is invalidated.

from uuid import UUID
from datetime import datetime, timezone
from app.domain.batch import Batch, BatchDetail
from app.domain.user import User


class BatchService:
    """
    Manages document batches and their lifecycle.
    """

    def __init__(self, batch_repo, audit_repo, cache):
        self.batch_repo = batch_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def create_batch(self, actor: User | None = None) -> Batch:
        """
        Create a new batch in 'pending' state.
        Called by the SFTP ingest worker (no actor) or an admin.
        :raises PermissionDenied: in Phase 2, if a non-system non-admin tries to call this
        """
        # Phase 1 stub
        return Batch(
            id=UUID("10000000-0000-0000-0000-000000000000"),
            status="pending",
            created_at=datetime.now(timezone.utc),
            prediction_count=0,
        )

    async def get_batch(self, batch_id: UUID) -> BatchDetail:
        """
        Retrieve a single batch including its predictions.
        :raises NotFound: if batch_id does not exist
        """
        # Phase 1 stub
        return BatchDetail(
            id=batch_id,
            status="processing",
            created_at=datetime.now(timezone.utc),
            prediction_count=3,
            predictions=[],
        )

    async def list_batches(self, skip: int = 0, limit: int = 20) -> list[Batch]:
        """
        Return a paginated list of batch summaries.
        """
        # Phase 1 stub
        return [
            Batch(
                id=UUID("10000000-0000-0000-0000-000000000001"),
                status="done",
                created_at=datetime.now(timezone.utc),
                prediction_count=5,
            ),
            Batch(
                id=UUID("10000000-0000-0000-0000-000000000002"),
                status="processing",
                created_at=datetime.now(timezone.utc),
                prediction_count=2,
            ),
        ]

    async def mark_processing(self, batch_id: UUID) -> Batch:
        """
        Transition a batch to 'processing' state.
        :raises InvalidStateTransition: in Phase 2, if batch is already 'done'
        :raises NotFound: if batch_id does not exist
        """
        # Phase 1 stub
        return Batch(
            id=batch_id,
            status="processing",
            created_at=datetime.now(timezone.utc),
            prediction_count=0,
        )

    async def mark_done(self, batch_id: UUID) -> Batch:
        """
        Transition a batch to 'done' state.
        :raises InvalidStateTransition: in Phase 2, if batch is 'pending'
            (must pass through 'processing' first)
        :raises NotFound: if batch_id does not exist
        """
        # Phase 1 stub
        return Batch(
            id=batch_id,
            status="done",
            created_at=datetime.now(timezone.utc),
            prediction_count=10,
        )
