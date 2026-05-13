# Location: app/services/prediction_service.py
# Main purpose: Business logic around predictions.
# Handles persisting new predictions from the inference worker,
# listing/recent predictions, and relabeling (with reviewer permissions
# and the confidence < 0.7 rule).
#
# Note: relabel does NOT overwrite predicted_class.  The model's original
# prediction is kept; the reviewer's correction goes into relabeled_class.
# This preserves the history needed for retraining and auditing.

from datetime import datetime, timezone

from app.domain.prediction import Prediction, PredictionCreate, PredictionRelabel
from app.domain.user import User, Role


class PredictionService:
    """
    Manages prediction records created by the ML worker.
    """

    def __init__(self, prediction_repo, audit_repo, cache):
        self.prediction_repo = prediction_repo
        self.audit_repo = audit_repo
        self.cache = cache

    async def save_prediction(self, data: PredictionCreate) -> Prediction:
        """
        Persist a new prediction record.
        Called by the inference worker after classifying an image.
        """
        # Phase 1 stub
        return Prediction(
            id="20000000-0000-0000-0000-000000000000",
            batch_id=data.batch_id,
            filename=data.filename,
            blob_key=data.blob_key,
            overlay_key=data.overlay_key,
            predicted_class=data.predicted_class,
            confidence=data.confidence,
            relabeled_class=None,
            created_at=datetime.now(timezone.utc),
        )

    async def get_by_id(self, prediction_id: str) -> Prediction:
        """
        Retrieve a single prediction by id.
        :raises NotFound: if no prediction with this id exists
        """
        return Prediction(
            id=prediction_id,
            batch_id="10000000-0000-0000-0000-000000000000",
            filename="doc1.tiff",
            blob_key="minio://documents/batches/b1/original/doc1.tiff",
            overlay_key="minio://documents/batches/b1/overlay/doc1.png",
            predicted_class="invoice",
            confidence=0.85,
            relabeled_class=None,
            created_at=datetime.now(timezone.utc),
        )

    async def get_predictions_for_batch(self, batch_id: str) -> list[Prediction]:
        """
        Return all predictions belonging to a specific batch.
        """
        return [
            Prediction(
                id="20000000-0000-0000-0000-000000000001",
                batch_id=batch_id,
                filename="doc1.tiff",
                blob_key="minio://documents/batches/b1/original/doc1.tiff",
                overlay_key="minio://documents/batches/b1/overlay/doc1.png",
                predicted_class="handwritten",
                confidence=0.95,
                relabeled_class=None,
                created_at=datetime.now(timezone.utc),
            )
        ]

    async def get_recent_predictions(self, limit: int = 10) -> list[Prediction]:
        """
        Return the most recent predictions across all batches.
        Phase 2: prediction_repo.list_recent(limit).
        """
        # Independent list - NOT delegated to get_predictions_for_batch
        now = datetime.now(timezone.utc)
        return [
            Prediction(
                id="20000000-0000-0000-0000-000000000010",
                batch_id="10000000-0000-0000-0000-000000000001",
                filename="recent1.tiff",
                blob_key="minio://documents/batches/b2/original/recent1.tiff",
                overlay_key="minio://documents/batches/b2/overlay/recent1.png",
                predicted_class="invoice",
                confidence=0.92,
                relabeled_class=None,
                created_at=now,
            ),
            Prediction(
                id="20000000-0000-0000-0000-000000000011",
                batch_id="10000000-0000-0000-0000-000000000002",
                filename="recent2.tiff",
                blob_key="minio://documents/batches/b3/original/recent2.tiff",
                overlay_key="minio://documents/batches/b3/overlay/recent2.png",
                predicted_class="resume",
                confidence=0.58,
                relabeled_class=None,
                created_at=now,
            ),
        ][:limit]

    async def relabel(
        self,
        prediction_id: str,
        update: PredictionRelabel,
        actor: User,
    ) -> Prediction:
        """
        Set the reviewer's corrected class for a prediction.
        Phase 2 will:
          1. Check actor.role is reviewer or admin
          2. Fetch the prediction (NotFound if missing)
          3. If actor is reviewer, require pred.confidence < 0.7
          4. Call prediction_repo.relabel(prediction_id, update.relabeled_class, actor.id)
          5. Invalidate predictions:recent and the parent batch cache
          6. Audit log: action="relabel", detail={"from": predicted_class, "to": relabeled_class}
        :raises PermissionDenied: if actor is not reviewer or admin
        :raises RelabelNotAllowed: if reviewer tries to relabel a high-confidence prediction
        :raises NotFound: if prediction_id does not exist
        """
        # Phase 1 stub - leaves predicted_class intact and sets relabeled_class
        return Prediction(
            id=prediction_id,
            batch_id="10000000-0000-0000-0000-000000000000",
            filename="doc1.tiff",
            blob_key="minio://documents/batches/b1/original/doc1.tiff",
            overlay_key="minio://documents/batches/b1/overlay/doc1.png",
            predicted_class="invoice",                # original model output, untouched
            confidence=0.65,
            relabeled_class=update.relabeled_class,   # reviewer's correction
            created_at=datetime.now(timezone.utc),
        )
