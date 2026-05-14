# File: app/api/deps.py

import os
from typing import AsyncGenerator

import casbin
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.infra.cache import (
    CacheInvalidator,
    RedisCacheInvalidator,
)
from app.services.batch_service import BatchService
from app.services.prediction_service import PredictionService
from app.services.user_service import UserService


# =========================
# Database Dependency
# =========================

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# =========================
# Cache Dependency
# =========================

async def get_cache() -> AsyncGenerator[CacheInvalidator, None]:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    cache = RedisCacheInvalidator(redis_url)
    try:
        yield cache
    finally:
        await cache.close()


# =========================
# Casbin Dependency (global enforcer from app.state)
# =========================

def get_enforcer(request: Request) -> casbin.Enforcer:
    return request.app.state.enforcer


# =========================
# Service Factories
# =========================

async def get_user_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheInvalidator = Depends(get_cache),
) -> UserService:
    return UserService(db, cache)


async def get_batch_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheInvalidator = Depends(get_cache),
) -> BatchService:
    return BatchService(db, cache)


async def get_prediction_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheInvalidator = Depends(get_cache),
) -> PredictionService:
    return PredictionService(db, cache)