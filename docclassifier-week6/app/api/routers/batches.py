# File: app/api/routers/batches.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi_cache.decorator import cache
import casbin

from app.api.deps import (
    get_batch_service,
    get_enforcer,
)
from app.api.routers.auth import current_domain_user
from app.domain.user import User
from app.infra.cache import (
    BATCHES_LIST_KEY,
    batch_key,
)
from app.services.batch_service import BatchService

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("/")
@cache(
    expire=60,
    key_builder=lambda func, namespace, request, response, *args, **kwargs: BATCHES_LIST_KEY,
)
async def list_batches(
    skip: int = 0,
    limit: int = 20,
    actor: User = Depends(current_domain_user),
    svc: BatchService = Depends(get_batch_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    allowed = enforcer.enforce(actor.role.value, "/batches", "GET")
    if not allowed:
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
    # Use generic path "/batches/detail" for Casbin enforcement
    allowed = enforcer.enforce(actor.role.value, "/batches/detail", "GET")
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await svc.get_batch(batch_id)