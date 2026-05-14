# File: app/api/routers/auth.py

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi_users import FastAPIUsers, BaseUserManager
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import User as UserORM
from app.db.session import engine
from app.domain.user import UserRead, UserCreate, User as DomainUser
from app.infra.vault import get_secret

# fastapi-users assumes SQLAlchemy's default autobegin=True (it issues
# execute() without opening a transaction first).  The shared
# AsyncSessionLocal has autobegin disabled so services can own transaction
# boundaries via `async with self.db.begin():`.  We give fastapi-users its
# own sessionmaker so the two regimes don't fight.
_AuthSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

router = APIRouter(prefix="/auth", tags=["auth"])


# =========================
# UserManager
# =========================

class UserManager(BaseUserManager[UserORM, str]):
    """Minimal user manager for fastapi-users."""

    reset_password_token_secret = get_secret("JWT_SECRET")
    verification_token_secret = get_secret("JWT_SECRET")

    def parse_id(self, value: str) -> str:
        return str(value)

    async def on_after_register(self, user: UserORM, request=None):
        pass  # No-op; no email verification required

    async def on_after_forgot_password(self, user: UserORM, token: str, request=None):
        pass

    async def on_after_request_verify(self, user: UserORM, token: str, request=None):
        pass


async def get_user_db():
    # Dedicated session for fastapi-users (autobegin enabled).  Does not
    # share with services so neither side fights over transaction control.
    async with _AuthSessionLocal() as session:
        yield SQLAlchemyUserDatabase(session, UserORM)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    yield UserManager(user_db)


# =========================
# Authentication
# =========================

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    secret = get_secret("JWT_SECRET")
    return JWTStrategy(secret=secret, lifetime_seconds=60 * 60 * 24)


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


# =========================
# FastAPIUsers instance
# =========================

fastapi_users = FastAPIUsers[UserORM, str](
    get_user_manager,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)


# =========================
# Domain user dependency
# =========================

async def current_domain_user(
    user: UserORM = Depends(current_active_user),
) -> DomainUser:
    """Convert ORM user to domain model."""
    return DomainUser.model_validate(user)


# =========================
# Routers
# =========================

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
)

router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/register",
)