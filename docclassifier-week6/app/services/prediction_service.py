# Location: app/services/prediction_service.py
# Main purpose: Business logic around predictions.
# Handles persisting new predictions from the inference worker,
# listing/recent predictions, and relabeling (with reviewer permissions
# and the confidence < 0.7 rule).

from uuid import UUID
from app.domain.prediction import Prediction
from app.domain.user import User


class PredictionService:
    """
    Manages prediction records created by the ML worker.
    """

    def __init__(self, prediction_repo, audit_repo, cache):
        """
        Inject dependencies.
        :param prediction_repo: PredictionRepository instance
        :param audit_repo: AuditRepository instance
        :param cache: CacheInvalidator instance
        """
        self.prediction_repo = prediction_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def save_prediction(
        self,
        batch_id: UUID,
        filename: str,
        blob_key: str,
        overlay_key: str,
        predicted_class: int,
        confidence: float,
    ) -> Prediction:
        """
        Persist a new prediction record.
        Called by the inference worker after classifying an image.
        :return: newly created Prediction domain model
        """
        # Phase 1 stub - returns a dummy prediction
        return Prediction(
            id=UUID("20000000-0000-0000-0000-000000000000"),
            batch_id=batch_id,
            filename=filename,
            blob_key=blob_key,
            overlay_key=overlay_key,
            predicted_class=predicted_class,
            confidence=confidence,
            is_reviewed=False,
        )

    async def get_by_id(self, prediction_id: UUID) -> Prediction:
        """
        Retrieve a single prediction by id.
        :raises NotFound: if no prediction with this id exists
        """
        # Phase 1 stub
        return Prediction(
            id=prediction_id,
            batch_id=UUID("10000000-0000-0000-0000-000000000000"),
            filename="doc1.tiff",
            blob_key="uploads/batch1/doc1.tiff",
            overlay_key="overlays/batch1/doc1.png",
            predicted_class=3,
            confidence=0.85,
            is_reviewed=False,
        )

    async def get_predictions_for_batch(self, batch_id: UUID) -> list[Prediction]:
        """
        Return all predictions belonging to a specific batch.
        """
        # Phase 1 stub - returns one dummy prediction for the given batch
        return [
            Prediction(
                id=UUID("20000000-0000-0000-0000-000000000001"),
                batch_id=batch_id,
                filename="doc1.tiff",
                blob_key="uploads/batch1/doc1.tiff",
                overlay_key="overlays/batch1/doc1.png",
                predicted_class=3,
                confidence=0.95,
                is_reviewed=False,
            )
        ]

    async def get_recent_predictions(self, limit: int = 10) -> list[Prediction]:
        """
        Return the most recent predictions across all batches.
        Phase 2: prediction_repo.list_recent(limit).
        """
        # Phase 1 stub - returns an independent list, NOT delegated to get_predictions_for_batch
        return [
            Prediction(
                id=UUID("20000000-0000-0000-0000-000000000010"),
                batch_id=UUID("10000000-0000-0000-0000-000000000001"),
                filename="recent1.tiff",
                blob_key="uploads/recent/recent1.tiff",
                overlay_key="overlays/recent/recent1.png",
                predicted_class=11,  # invoice
                confidence=0.92,
                is_reviewed=False,
            ),
            Prediction(
                id=UUID("20000000-0000-0000-0000-000000000011"),
                batch_id=UUID("10000000-0000-0000-0000-000000000002"),
                filename="recent2.tiff",
                blob_key="uploads/recent/recent2.tiff",
                overlay_key="overlays/recent/recent2.png",
                predicted_class=14,  # resume
                confidence=0.58,
                is_reviewed=False,
            ),
        ][:limit]

    async def relabel(
        self,
        prediction_id: UUID,
        new_class: int,
        actor: User,
    ) -> Prediction:
        """
        Change the class label of a prediction.
        Only reviewers and admins may relabel.
        Reviewers can only relabel predictions with confidence < 0.7.
        :raises PermissionDenied: if actor is not reviewer or admin
        :raises RelabelNotAllowed: if reviewer tries to relabel a high-confidence prediction
        :raises NotFound: if prediction_id does not exist
        """
        # Phase 1 stub - returns a prediction with the new label
        return Prediction(
            id=prediction_id,
            batch_id=UUID("10000000-0000-0000-0000-000000000000"),
            filename="doc1.tiff",
            blob_key="uploads/batch1/doc1.tiff",
            overlay_key="overlays/batch1/doc1.png",
            predicted_class=new_class,
            confidence=0.65,
            is_reviewed=True,
        )
