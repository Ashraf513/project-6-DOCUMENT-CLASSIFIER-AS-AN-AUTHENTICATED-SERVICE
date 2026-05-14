# Location: app/repositories/audit_repo.py
# Fixed version – does NOT commit; transaction is handled by services.

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog as AuditLogORM
from app.domain.audit import AuditLogEntry


class AuditRepo:
    """Repository for AuditLog operations (write-only, immutable)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        actor_id: Optional[str],
        action: str,
        target: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create an audit log entry (does NOT commit).
        Returns the new log ID.
        """
        log_id = str(uuid.uuid4())
        log_orm = AuditLogORM(
            id=log_id,
            actor_id=actor_id,
            action=action,
            target=target,
            details=details,
        )
        self.session.add(log_orm)
        # No commit – the service will commit
        return log_id

    async def get_by_actor(self, actor_id: str, limit: int = 100) -> List[AuditLogORM]:
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.actor_id == actor_id)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_action(self, action: str, limit: int = 100) -> List[AuditLogORM]:
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.action == action)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_target(self, target: str, limit: int = 100) -> List[AuditLogORM]:
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.target == target)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_recent(self, limit: int = 100) -> List[AuditLogEntry]:
        result = await self.session.execute(
            select(AuditLogORM)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return [AuditLogEntry.model_validate(e) for e in result.scalars().all()]