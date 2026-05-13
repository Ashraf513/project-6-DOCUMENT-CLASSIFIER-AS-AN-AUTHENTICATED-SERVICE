"""
User Repository — ORM layer for User entity.

This repository converts between ORM models (app.db.models.User) and
domain models (app.domain.user.User, UserCreate, etc.).

Guidelines:
1. Accept domain models as input (UserCreate, UserRoleUpdate, etc.)
2. Always return domain models, never ORM objects
3. Let the ORM handle database details (relationships, timestamps)
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User as UserORM
from app.domain.user import User, UserCreate, UserRoleUpdate


class UserRepo:
    """Repository for User operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_create: UserCreate, hashed_password: str) -> User:
        """Create a new user."""
        user_orm = UserORM(
            id=str(uuid.uuid4()),
            email=user_create.email,
            hashed_password=hashed_password,
            role=user_create.role,
        )
        self.session.add(user_orm)
        await self.session.commit()
        await self.session.refresh(user_orm)
        return User.model_validate(user_orm)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Fetch user by ID."""
        result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def get_by_email(self, email: str) -> Optional[User]:
        """Fetch user by email."""
        result = await self.session.execute(select(UserORM).where(UserORM.email == email))
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def update_role(self, user_id: str, role_update: UserRoleUpdate) -> Optional[User]:
        """Update user role by ID."""
        stmt = update(UserORM).where(UserORM.id == user_id).values(role=role_update.role).returning(UserORM)
        result = await self.session.execute(stmt)
        await self.session.commit()
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None

    async def toggle_active(self, user_id: str, is_active: bool) -> Optional[User]:
        """Toggle user active status."""
        stmt = update(UserORM).where(UserORM.id == user_id).values(is_active=is_active).returning(UserORM)
        result = await self.session.execute(stmt)
        await self.session.commit()
        user_orm = result.scalar_one_or_none()
        return User.model_validate(user_orm) if user_orm else None