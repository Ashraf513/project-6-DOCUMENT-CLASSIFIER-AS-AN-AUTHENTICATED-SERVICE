# Location: app/services/batch_service.py
# Main purpose: Business logic for batch management.
# This service handles batch creation, status transitions
# (pending -> processing -> done | failed), listing, and retrieval.
# It ensures state changes are audited and cache is invalidated.

from datetime import datetime, timezone

from app.domain.batch import Batch, BatchStatus, BatchCreate
from app.domain.user import User


class BatchService:
    """
    Manages document batches and their lifecycle.
    """

    def __init__(self, batch_repo, audit_repo, cache):
        self.batch_repo = batch_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def create_batch(
        self,
        data: BatchCreate | None = None,
        actor: User | None = None,
    ) -> Batch:
        """
        Create a new batch in 'pending' state.
        Called by the SFTP ingest worker (no actor) or an admin.
        :param data: optional BatchCreate input; if None, a fresh one is generated
        :raises PermissionDenied: in Phase 2, if a non-system non-admin tries to call this
        """
        if data is None:
            data = BatchCreate()

        # Phase 1 stub
        return Batch(
            id=data.id,
            status=BatchStatus.pending,
            file_count=data.file_count,
            created_at=datetime.now(timezone.utc),
        )

    async def get_batch(self, batch_id: str) -> Batch:
        """
        Retrieve a single batch summary.
        The router composes the response by also calling
        prediction_service.get_predictions_for_batch(batch_id).
        :raises NotFound: if batch_id does not exist
        """
        # Phase 1 stub
        return Batch(
            id=batch_id,
            status=BatchStatus.processing,
            file_count=3,
            created_at=datetime.now(timezone.utc),
        )

    async def list_batches(self, skip: int = 0, limit: int = 20) -> list[Batch]:
        """
        Return a paginated list of batch summaries.
        """
        now = datetime.now(timezone.utc)
        return [
            Batch(
                id="10000000-0000-0000-0000-000000000001",
                status=BatchStatus.done,
                file_count=5,
                created_at=now,
            ),
            Batch(
                id="10000000-0000-0000-0000-000000000002",
                status=BatchStatus.processing,
                file_count=2,
                created_at=now,
            ),
        ]

    async def mark_processing(self, batch_id: str) -> Batch:
        """
        Transition a batch to 'processing' state.
        :raises InvalidStateTransition: in Phase 2, if batch is already terminal (done/failed)
        :raises NotFound: if batch_id does not exist
        """
        return Batch(
            id=batch_id,
            status=BatchStatus.processing,
            file_count=0,
            created_at=datetime.now(timezone.utc),
        )

    async def mark_done(self, batch_id: str) -> Batch:
        """
        Transition a batch to 'done' state.
        :raises InvalidStateTransition: in Phase 2, if batch is 'pending'
            (must pass through 'processing' first) or already terminal.
        :raises NotFound: if batch_id does not exist
        """
        return Batch(
            id=batch_id,
            status=BatchStatus.done,
            file_count=10,
            created_at=datetime.now(timezone.utc),
        )

    async def mark_failed(self, batch_id: str) -> Batch:
        """
        Transition a batch to 'failed' state.
        Called by the inference worker when an inference job exhausts retries.
        :raises NotFound: if batch_id does not exist
        """
        return Batch(
            id=batch_id,
            status=BatchStatus.failed,
            file_count=0,
            created_at=datetime.now(timezone.utc),
        )
