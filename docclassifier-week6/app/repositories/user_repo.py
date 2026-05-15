# Location: app/repositories/user_repo.py
# User repository – no internal commits; service handles transaction.

from __future__ import annotations

from typing import List, Optional

import uuid
from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.db.models import User as UserORM
from app.domain.user import User, Role, UserCreate


class UserRepo:
    """Repository for User operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_create: UserCreate) -> User:
        """Create a new user (password already hashed)."""
        now = datetime.now(timezone.utc)
        user_orm = UserORM(
            id=str(uuid.uuid4()),
            email=user_create.email,
            hashed_password=user_create.password,
            role=user_create.role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(user_orm)
        # No commit – service manages transaction
        return User.model_validate(user_orm)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(UserORM).where(UserORM.email == email)
        )
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[User]:
        """List all users."""
        result = await self.session.execute(
            select(UserORM).offset(offset).limit(limit).order_by(UserORM.created_at.desc())
        )
        user_orms = result.scalars().all()
        return [User.model_validate(u) for u in user_orms]

    async def count_by_role(self, role: Role) -> int:
        """Count users with a specific role."""
        result = await self.session.execute(
            select(func.count(UserORM.id)).where(UserORM.role == role)
        )
        return result.scalar() or 0

    async def update_role(self, user_id: str, new_role: Role) -> Optional[User]:
        """Update user role (does NOT commit)."""
        stmt = (
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(role=new_role)
            .returning(UserORM)
        )
        result = await self.session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def delete(self, user_id: str) -> bool:
        """Hard-delete a user (does NOT commit).
        Uses a raw DELETE so the DB ondelete='SET NULL' on audit_log.actor_id
        fires correctly — audit history is preserved with actor_id = NULL."""
        stmt   = sa_delete(UserORM).where(UserORM.id == user_id)
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def update_active(self, user_id: str, is_active: bool) -> Optional[User]:
        """Activate/deactivate user (does NOT commit)."""
        stmt = (
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(is_active=is_active)
            .returning(UserORM)
        )
        result = await self.session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None