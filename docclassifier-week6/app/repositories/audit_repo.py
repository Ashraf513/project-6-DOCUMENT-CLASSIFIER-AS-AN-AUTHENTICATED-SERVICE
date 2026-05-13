"""
Audit Repository — ORM layer for AuditLog entity.

This repository handles audit log writes only (immutable event log).
Audit logs are created by services when significant actions occur.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog as AuditLogORM


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
        Create an audit log entry.
        
        Args:
            actor_id: User ID performing the action (None if system action)
            action: Action name (e.g., "role_change", "relabel", "batch_state_change")
            target: Target entity (e.g., "user:uuid-123", "prediction:uuid-456")
            details: Extra metadata as dict (e.g., {"old_role": "auditor", "new_role": "reviewer"})
        
        Returns:
            The created audit log ID
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
        await self.session.commit()
        return log_id

    async def get_by_actor(self, actor_id: str, limit: int = 100) -> List[AuditLogORM]:
        """Get all audit logs created by a specific user."""
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.actor_id == actor_id)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_action(self, action: str, limit: int = 100) -> List[AuditLogORM]:
        """Get all audit logs for a specific action type."""
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.action == action)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_by_target(self, target: str, limit: int = 100) -> List[AuditLogORM]:
        """Get all audit logs for a specific target entity."""
        result = await self.session.execute(
            select(AuditLogORM)
            .where(AuditLogORM.target == target)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def list_recent(self, limit: int = 100) -> List[AuditLogORM]:
        """Get recent audit logs across all actions."""
        result = await self.session.execute(
            select(AuditLogORM)
            .order_by(AuditLogORM.timestamp.desc())
            .limit(limit)
        )
        return result.scalars().all()