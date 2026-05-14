# File: app/api/routers/batches.py

import casbin
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from app.api.deps import get_batch_service, get_enforcer
from app.api.routers.auth import current_domain_user
from app.domain.user import User
from app.infra.cache import BATCHES_LIST_KEY, batch_key
from app.services.batch_service import BatchService
from app.services.exceptions import NotFound

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("/")
@cache(
    expire=60,
    key_builder=lambda func, namespace, request, response, *args, **kwargs: BATCHES_LIST_KEY,
)
async def list_batches(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    actor: User = Depends(current_domain_user),
    svc: BatchService = Depends(get_batch_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/batches", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await svc.list_batches(skip=skip, limit=limit)


@router.get("/{batch_id}")
@cache(
    expire=60,
    key_builder=lambda func, namespace, request, response, *args, **kwargs:
        batch_key(kwargs["kwargs"]["batch_id"]),
)
async def get_batch(
    batch_id: str,
    actor: User = Depends(current_domain_user),
    svc: BatchService = Depends(get_batch_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/batches/detail", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return await svc.get_batch(batch_id)
    except NotFound:
        raise HTTPException(status_code=404, detail="Batch not found")
