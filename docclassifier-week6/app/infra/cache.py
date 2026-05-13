"""
Cache invalidation abstraction used by the service layer.

Services depend on the CacheInvalidator protocol – not on Redis directly –
so they can be tested with an in-memory stub.

The concrete RedisCacheInvalidator wires redis.asyncio and should be
instantiated in deps.py from the same REDIS_URL that fastapi-cache2 uses.
"""

from __future__ import annotations

import os
from typing import Protocol

import redis.asyncio as redis


# ---- Cache key constants -------------------------------------------------
# Sync these names with Hussien before he writes the fastapi-cache2 key
# builder.  Whatever string his decorator caches under MUST equal the
# string we delete here, or invalidation silently does nothing.

USERS_LIST_KEY          = "users:list"
BATCHES_LIST_KEY        = "batches:list"
PREDICTIONS_RECENT_KEY  = "predictions:recent"


def user_me_key(user_id: str) -> str:
    """Cache key for the authenticated user's /me response."""
    return f"user:me:{user_id}"


def batch_key(batch_id: str) -> str:
    """Cache key for a single batch (used for GET /batches/{id})."""
    return f"batch:{batch_id}"


def predictions_batch_key(batch_id: str) -> str:
    """Cache key for predictions of a specific batch."""
    return f"predictions:batch:{batch_id}"


# ---- Interface -----------------------------------------------------------

class CacheInvalidator(Protocol):
    """Anything services need to ask of the cache."""

    async def delete(self, key: str) -> None: ...

    async def delete_many(self, *keys: str) -> None: ...


# ---- In-memory implementation (tests, local dev without Redis) -----------

class InMemoryCacheInvalidator:
    """No-op-style cache used in tests and before Redis is wired."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_many(self, *keys: str) -> None:
        self.deleted.extend(keys)


# ---- Redis implementation (production) -----------------------------------

class RedisCacheInvalidator:
    """
    Real cache invalidator backed by Redis.

    Instantiate it with the same REDIS_URL used by fastapi-cache2, e.g.:
        REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        cache = RedisCacheInvalidator(REDIS_URL)
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=False)

    async def delete(self, key: str) -> None:
        """Delete a single cache key."""
        await self._redis.delete(key)

    async def delete_many(self, *keys: str) -> None:
        """Delete multiple cache keys in one round trip."""
        if keys:
            await self._redis.delete(*keys)

    async def close(self) -> None:
        """Release the Redis connection."""
        await self._redis.close()