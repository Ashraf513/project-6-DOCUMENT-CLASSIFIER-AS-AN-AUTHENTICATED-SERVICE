"""
Cache invalidation abstraction used by the service layer.

Services depend on CacheInvalidator (a Protocol) — not on Redis directly —
so they can be tested with an in-memory stub.

RedisCacheInvalidator wraps a shared redis.asyncio client that is created
once in app lifespan (main.py) and injected via deps.py.  Creating a new
connection pool per request is wasteful; use from_client() instead.
"""

from __future__ import annotations

from typing import Protocol

import redis.asyncio as redis


# ---- Cache key constants -------------------------------------------------------

USERS_LIST_KEY         = "users:list"
BATCHES_LIST_KEY       = "batches:list"
PREDICTIONS_RECENT_KEY = "predictions:recent"


def user_me_key(user_id: str) -> str:
    return f"user:me:{user_id}"


def batch_key(batch_id: str) -> str:
    return f"batch:{batch_id}"


def predictions_batch_key(batch_id: str) -> str:
    return f"predictions:batch:{batch_id}"


# ---- Interface -----------------------------------------------------------------

class CacheInvalidator(Protocol):
    async def delete(self, key: str) -> None: ...
    async def delete_many(self, *keys: str) -> None: ...


# ---- In-memory implementation (tests, local dev without Redis) -----------------

class InMemoryCacheInvalidator:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_many(self, *keys: str) -> None:
        self.deleted.extend(keys)


# ---- Redis implementation (production) ----------------------------------------

class RedisCacheInvalidator:
    """
    Cache invalidator backed by a shared Redis connection pool.

    Preferred constructor: RedisCacheInvalidator.from_client(redis_client)
    where redis_client is created once in the app lifespan.

    The direct constructor (passing a URL) is kept for backward compat /
    standalone scripts, but should NOT be used per request.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=False)
        self._owns_pool = True

    @classmethod
    def from_client(cls, client: redis.Redis) -> "RedisCacheInvalidator":
        """Wrap an existing shared Redis client — no new pool is created."""
        inst = object.__new__(cls)
        inst._redis = client
        inst._owns_pool = False
        return inst

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    async def delete_many(self, *keys: str) -> None:
        if keys:
            await self._redis.delete(*keys)

    async def close(self) -> None:
        if self._owns_pool:
            await self._redis.aclose()
