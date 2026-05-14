# Location: app/services/prediction_service.py
# Business logic around predictions.
# Handles saving new predictions, listing, and relabeling
# with reviewer permissions and the confidence < 0.7 rule.

from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.prediction import Prediction, PredictionCreate, PredictionRelabel
from app.domain.user import User, Role
from app.repositories.prediction_repo import PredictionRepo
from app.repositories.audit_repo import AuditRepo
from app.infra.cache import (
    CacheInvalidator,
    PREDICTIONS_RECENT_KEY,
    batch_key,
    predictions_batch_key,
)
from app.services.exceptions import (
    PermissionDenied,
    NotFound,
    RelabelNotAllowed,
)


class PredictionService:
    """
    Manages prediction records created by the ML worker.
    """

    def __init__(self, db: AsyncSession, cache: CacheInvalidator):
        self.db = db
        self.cache = cache
        self.prediction_repo = PredictionRepo(db)
        self.audit_repo = AuditRepo(db)

    async def save_prediction(
        self,
        batch_id: str,
        data: PredictionCreate,
    ) -> Prediction:
        async with self.db.begin():
            prediction = await self.prediction_repo.create(batch_id, data)

        await self.cache.delete(PREDICTIONS_RECENT_KEY)
        await self.cache.delete(batch_key(batch_id))
        await self.cache.delete(predictions_batch_key(batch_id))
        return prediction

    async def get_by_id(self, prediction_id: str) -> Prediction:
        async with self.db.begin():
            pred = await self.prediction_repo.get_by_id(prediction_id)
            if not pred:
                raise NotFound("Prediction not found")
            return pred

    async def get_predictions_for_batch(self, batch_id: str) -> list[Prediction]:
        async with self.db.begin():
            return await self.prediction_repo.get_by_batch_id(batch_id)

    async def get_recent_predictions(self, limit: int = 10) -> list[Prediction]:
        async with self.db.begin():
            return await self.prediction_repo.get_recent(limit=limit)

    async def relabel(
        self,
        prediction_id: str,
        update: PredictionRelabel,
        actor: User,
    ) -> Prediction:
        if actor.role not in (Role.admin, Role.reviewer):
            raise PermissionDenied("Only reviewers and admins can relabel")

        async with self.db.begin():
            pred = await self.prediction_repo.get_by_id(prediction_id)
            if not pred:
                raise NotFound("Prediction not found")

            if actor.role == Role.reviewer and pred.confidence >= 0.7:
                raise RelabelNotAllowed(
                    "Reviewers can only relabel predictions with confidence < 0.7"
                )

            updated = await self.prediction_repo.relabel(prediction_id, update)
            if not updated:
                raise NotFound("Prediction not found during relabel")

            await self.audit_repo.create(
                actor_id=actor.id,
                action="relabel",
                target=f"prediction:{prediction_id}",
                details={
                    "from": pred.predicted_class,
                    "to": update.relabeled_class,
                },
            )

        await self.cache.delete(PREDICTIONS_RECENT_KEY)
        await self.cache.delete(batch_key(pred.batch_id))
        await self.cache.delete(predictions_batch_key(pred.batch_id))
        return updated