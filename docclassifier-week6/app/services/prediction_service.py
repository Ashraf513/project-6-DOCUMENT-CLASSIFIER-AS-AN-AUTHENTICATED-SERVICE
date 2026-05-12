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
        confidence: float
    ) -> Prediction:
        """
        Persist a new prediction record.
        Called by the inference worker after classifying an image.
        :param batch_id: UUID of the batch the document belongs to
        :param filename: original filename of the document (SFTP name)
        :param blob_key: MinIO key where the original TIFF is stored
        :param overlay_key: MinIO key where the annotated overlay PNG is stored
        :param predicted_class: integer class label (0-15)
        :param confidence: confidence score of the prediction [0,1]
        :return: newly created Prediction domain model
        """
        # Phase 1 stub – returns a dummy prediction
        return Prediction(
            id=UUID("20000000-0000-0000-0000-000000000000"),
            batch_id=batch_id,
            filename=filename,
            blob_key=blob_key,
            overlay_key=overlay_key,
            predicted_class=predicted_class,
            confidence=confidence,
            is_reviewed=False
        )

    async def get_predictions_for_batch(self, batch_id: UUID) -> list[Prediction]:
        """
        Return all predictions belonging to a specific batch.
        :param batch_id: UUID of the batch
        :return: list of Prediction domain models
        """
        # Phase 1 stub – returns one dummy prediction for the given batch
        return [
            Prediction(
                id=UUID("20000000-0000-0000-0000-000000000001"),
                batch_id=batch_id,
                filename="doc1.tiff",
                blob_key="uploads/batch1/doc1.tiff",
                overlay_key="overlays/batch1/doc1.png",
                predicted_class=3,  # e.g., "handwritten"
                confidence=0.95,
                is_reviewed=False
            )
        ]

    async def get_recent_predictions(self, limit: int = 10) -> list[Prediction]:
        """
        Return the most recent predictions across all batches.
        :param limit: maximum number of results
        :return: list of Prediction domain models
        """
        # Phase 1 stub – delegate to get_predictions_for_batch with a dummy batch id
        return await self.get_predictions_for_batch(
            UUID("00000000-0000-0000-0000-000000000000")
        )

    async def relabel(
        self,
        prediction_id: UUID,
        new_class: int,
        actor: User
    ) -> Prediction:
        """
        Change the class label of a prediction.
        Only reviewers (and admins) may relabel.
        Reviewers can only relabel predictions with confidence < 0.7.
        :param prediction_id: UUID of the prediction to relabel
        :param new_class: new class label (0-15)
        :param actor: the user performing the relabel (must be reviewer or admin)
        :return: updated Prediction domain model
        :raises PermissionError: if actor lacks permissions or confidence >= 0.7
        """
        # Phase 1 stub – returns a prediction with the new label and a low confidence
        return Prediction(
            id=prediction_id,
            batch_id=UUID("10000000-0000-0000-0000-000000000000"),
            filename="doc1.tiff",
            blob_key="uploads/batch1/doc1.tiff",
            overlay_key="overlays/batch1/doc1.png",
            predicted_class=new_class,
            confidence=0.65,   # low enough to pass the relabel check
            is_reviewed=True    # indicates a human review was done
        )