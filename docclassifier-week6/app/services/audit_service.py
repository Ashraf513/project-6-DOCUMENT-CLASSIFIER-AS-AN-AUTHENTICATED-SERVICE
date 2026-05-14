# Location: app/services/audit_service.py
# Purpose: Business logic for audit log retrieval.
# Keeps the API layer pure: routers never touch repositories or SQL.

from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.audit_repo import AuditRepo
from app.domain.audit import AuditLogEntry


class AuditService:
    """Read‑only service for the immutable audit log."""

    def __init__(self, db: AsyncSession):
        self.audit_repo = AuditRepo(db)

    async def list_recent(self, limit: int = 100) -> list[AuditLogEntry]:
        """Return the most recent audit entries."""
        return await self.audit_repo.list_recent(limit=limit)