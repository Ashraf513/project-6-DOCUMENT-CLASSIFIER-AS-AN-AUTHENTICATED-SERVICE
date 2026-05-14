# Location: app/repositories/user_repo.py
# User repository — no internal commits; service handles transaction.

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User as UserORM
from app.domain.user import User, Role, UserCreate


class UserRepo:
    """Repository for User operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_create: UserCreate, hashed_credential: str) -> User:
        """Create a new user. Caller (UserService) supplies the pre-hashed credential."""
        now = datetime.now(timezone.utc)
        user_orm = UserORM(
            id=str(uuid.uuid4()),
            email=str(user_create.email),
            hashed_password=hashed_credential,
            role=user_create.role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(user_orm)
        await self.session.flush()  # populate server-generated values before returning
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
        result = await self.session.execute(
            select(UserORM).offset(offset).limit(limit).order_by(UserORM.created_at.desc())
        )
        return [User.model_validate(u) for u in result.scalars().all()]

    async def count_by_role(self, role: Role) -> int:
        result = await self.session.execute(
            select(func.count(UserORM.id)).where(UserORM.role == role)
        )
        return result.scalar() or 0

    async def update_role(self, user_id: str, new_role: Role) -> Optional[User]:
        stmt = (
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(role=new_role)
            .returning(UserORM)
        )
        result = await self.session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def update_active(self, user_id: str, is_active: bool) -> Optional[User]:
        stmt = (
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(is_active=is_active)
            .returning(UserORM)
        )
        result = await self.session.execute(stmt)
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None
