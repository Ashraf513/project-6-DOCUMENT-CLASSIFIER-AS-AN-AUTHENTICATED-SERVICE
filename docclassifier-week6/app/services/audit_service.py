from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.audit import AuditLogEntry
from app.repositories.audit_repo import AuditRepo


class AuditService:
    """Read-only access to the audit log. Owns its own transaction."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_repo = AuditRepo(db)

    async def list_recent(self, limit: int = 100) -> list[AuditLogEntry]:
        async with self.db.begin():
            return await self.audit_repo.list_recent(limit=limit)
