# File: app/api/routers/auth.py

import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastapi import APIRouter, Depends
from fastapi_users import FastAPIUsers, BaseUserManager
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from app.db.models import User as UserORM
from app.db.session import engine
from app.domain.user import UserRead, UserCreate, User as DomainUser
from app.infra.vault import get_secret

# fastapi-users needs its own session maker with autobegin=True
# (it issues execute() without opening an explicit transaction).
_AuthSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

router = APIRouter(prefix="/auth", tags=["auth"])


# =========================
# UserManager
# =========================

class UserManager(BaseUserManager[UserORM, str]):
    """Minimal user manager. Secrets fetched from Vault at access time, not at import."""

    @property
    def reset_password_token_secret(self) -> str:   # C-5: property, not class var
        return get_secret("JWT_SECRET")

    @property
    def verification_token_secret(self) -> str:     # C-5: property, not class var
        return get_secret("JWT_SECRET")

    def parse_id(self, value: str) -> str:
        return str(value)

    async def on_after_register(self, user: UserORM, request=None):
        pass

    async def on_after_forgot_password(self, user: UserORM, token: str, request=None):
        pass

    async def on_after_request_verify(self, user: UserORM, token: str, request=None):
        pass


async def get_user_db():
    async with _AuthSessionLocal() as session:
        yield SQLAlchemyUserDatabase(session, UserORM)


async def get_user_manager(
    user_db: SQLAlchemyUserDatabase = Depends(get_user_db),
):
    yield UserManager(user_db)


# =========================
# Authentication backend
# =========================

bearer_transport = BearerTransport(tokenUrl="auth/jwt/login")


def get_jwt_strategy() -> JWTStrategy:
    secret   = get_secret("JWT_SECRET")
    lifetime = int(os.getenv("JWT_LIFETIME_SECONDS", str(60 * 60 * 24)))  # L-3: configurable
    return JWTStrategy(secret=secret, lifetime_seconds=lifetime)


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
    return DomainUser.model_validate(user)


# =========================
# Routers — login only; registration is admin-invite via POST /users/  (H-2)
# =========================

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
)

# NOTE: The open /auth/register endpoint is intentionally removed.
# New users are created by admins via POST /users/ which enforces role checks.
# The first admin account must be seeded via the migrate container or a CLI script.