# File: app/api/routers/audit.py

import casbin
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_audit_service, get_enforcer
from app.api.routers.auth import current_domain_user
from app.domain.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/")
async def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    actor: User = Depends(current_domain_user),
    svc: AuditService = Depends(get_audit_service),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    if not enforcer.enforce(actor.role.value, "/audit", "GET"):
        raise HTTPException(status_code=403, detail="Forbidden")
    return await svc.list_recent(limit=limit)
