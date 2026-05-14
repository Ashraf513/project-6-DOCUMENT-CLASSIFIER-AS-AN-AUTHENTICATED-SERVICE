# File: app/api/routers/predictions.py

import casbin
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from app.api.deps import get_enforcer, get_prediction_service
from app.api.routers.auth import current_domain_user
from app.domain.prediction import PredictionRelabel
from app.domain.user import User
from app.infra.cache import PREDICTIONS_RECENT_KEY, predictions_batch_key
from app.services.exceptions import NotFound, PermissionDenied, RelabelNotAllowed
from app.services.prediction_service import PredictionService

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("/recent")
@cache(
    expire=30,
    key_builder=lambda func, namespace, request, response, *args, **kwargs: PREDICTIONS_RECENT_KEY,
)
async def recent_predictions(
    limit: int = Query(default=10, ge=1, le=100),
    actor: User = Depends(current_domain_user),
    svc: PredictionService = Depends(get_prediction_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/predictions/recent", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await svc.get_recent_predictions(limit=limit)


@router.get("/batch/{batch_id}")
@cache(
    expire=60,
    key_builder=lambda func, namespace, request, response, *args, **kwargs:
        predictions_batch_key(kwargs["kwargs"]["batch_id"]),
)
async def predictions_for_batch(
    batch_id: str,
    actor: User = Depends(current_domain_user),
    svc: PredictionService = Depends(get_prediction_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/predictions/batch", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await svc.get_predictions_for_batch(batch_id)


@router.patch("/{prediction_id}/relabel")
async def relabel_prediction(
    prediction_id: str,
    update: PredictionRelabel,
    actor: User = Depends(current_domain_user),
    svc: PredictionService = Depends(get_prediction_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/predictions/relabel", "PATCH"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return await svc.relabel(prediction_id, update, actor)
    except PermissionDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except RelabelNotAllowed:
        raise HTTPException(
            status_code=403,
            detail="Reviewers may only relabel low-confidence predictions",
        )
    except NotFound:
        raise HTTPException(status_code=404, detail="Prediction not found")
