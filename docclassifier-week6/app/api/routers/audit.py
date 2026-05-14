# File: app/api/routers/audit.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import casbin

from app.api.deps import get_db, get_enforcer
from app.api.routers.auth import current_domain_user
from app.domain.user import User
from app.services.audit_service import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/")
async def list_audit_logs(
    limit: int = 100,
    actor: User = Depends(current_domain_user),
    db: AsyncSession = Depends(get_db),
    enforcer: casbin.Enforcer = Depends(get_enforcer),
):
    allowed = enforcer.enforce(actor.role.value, "/audit", "GET")
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")

    async with db.begin():
        svc = AuditService(db)
        return await svc.list_recent(limit=limit)