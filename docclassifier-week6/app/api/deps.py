# File: app/api/deps.py

from typing import AsyncGenerator

import casbin
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.infra.cache import CacheInvalidator, RedisCacheInvalidator
from app.services.audit_service import AuditService
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
# Cache Dependency — uses the shared pool from app.state (H-4)
# =========================

def get_cache(request: Request) -> CacheInvalidator:
    return RedisCacheInvalidator.from_client(request.app.state.redis)


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


async def get_audit_service(
    db: AsyncSession = Depends(get_db),
) -> AuditService:
    return AuditService(db)
