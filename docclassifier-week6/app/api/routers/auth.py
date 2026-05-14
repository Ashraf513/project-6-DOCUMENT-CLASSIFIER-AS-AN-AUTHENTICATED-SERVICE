# File: app/api/routers/auth.py

import os
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.models import User
from app.domain.user import UserRead, UserCreate
from app.infra.vault import get_secret

router = APIRouter(prefix="/auth", tags=["auth"])


bearer_transport = BearerTransport(
    tokenUrl="auth/jwt/login"
)


def get_jwt_strategy() -> JWTStrategy:
    secret = get_secret("JWT_SECRET")

    return JWTStrategy(
        secret=secret,
        lifetime_seconds=60 * 60 * 24,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)


async def get_user_db(
    session: AsyncSession = Depends(get_db),
):
    yield SQLAlchemyUserDatabase(
        session,
        User,
    )


fastapi_users = FastAPIUsers[User, str](
    get_user_db,
    [auth_backend],
)

current_active_user = fastapi_users.current_user(active=True)

router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
)

router.include_router(
    fastapi_users.get_register_router(
        UserRead,
        UserCreate,
    ),
    prefix="/register",
)