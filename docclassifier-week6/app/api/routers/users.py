# File: app/api/routers/users.py

import casbin
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_cache.decorator import cache

from app.api.deps import get_enforcer, get_user_service
from app.api.routers.auth import current_domain_user
from app.domain.user import User, UserCreate, UserRoleUpdate
from app.infra.cache import USERS_LIST_KEY, user_me_key
from app.services.exceptions import LastAdminError, NotFound, PermissionDenied
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


async def _guard_list_users(
    actor: User = Depends(current_domain_user),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
) -> None:
    """Casbin check as a dependency so it runs before the cache is consulted."""
    if not enforcer.enforce(actor.role.value, "/users", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/me")
@cache(
    expire=120,
    key_builder=lambda func, namespace, request, response, *args, **kwargs:
        user_me_key(kwargs["kwargs"]["user"].id),
)
async def get_me(
    user: User = Depends(current_domain_user),
    svc: UserService = Depends(get_user_service),
):
    return await svc.get_me(user.id)


@router.get("/")
@cache(
    expire=60,
    key_builder=lambda func, namespace, request, response, *args, **kwargs: USERS_LIST_KEY,
)
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    actor: User = Depends(current_domain_user),
    svc: UserService = Depends(get_user_service),
    _: None = Depends(_guard_list_users),
):
    try:
        return await svc.list_users(actor=actor, skip=skip, limit=limit)
    except PermissionDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/")
async def create_user(
    data: UserCreate,
    actor: User = Depends(current_domain_user),
    svc: UserService = Depends(get_user_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/users", "POST"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return await svc.create_user(data, actor)
    except PermissionDenied:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.patch("/{user_id}/role")
async def change_role(
    user_id: str,
    update: UserRoleUpdate,
    actor: User = Depends(current_domain_user),
    svc: UserService = Depends(get_user_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/users/role", "PATCH"):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return await svc.change_role(user_id, update, actor)
    except PermissionDenied:
        raise HTTPException(status_code=403, detail="Forbidden")
    except NotFound:
        raise HTTPException(status_code=404, detail="User not found")
    except LastAdminError:
        raise HTTPException(status_code=400, detail="Cannot demote the last admin")
