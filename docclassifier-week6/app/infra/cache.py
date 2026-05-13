"""
Cache invalidation abstraction used by the service layer.

Services depend on the CacheInvalidator protocol - not on Redis directly -
so they can be tested with an in-memory stub.

The concrete RedisCacheInvalidator wires fastapi-cache2 / redis.asyncio
in Card 3.  For now this provides the interface + an in-memory implementation
suitable for unit tests and local development.
"""

from __future__ import annotations

from typing import Protocol


# ---- Cache key constants -------------------------------------------------
# Sync these names with Hussien before he writes the fastapi-cache2 key
# builder.  Whatever string his decorator caches under MUST equal the
# string we delete here, or invalidation silently does nothing.

USERS_LIST_KEY          = "users:list"
BATCHES_LIST_KEY        = "batches:list"
PREDICTIONS_RECENT_KEY  = "predictions:recent"


def user_me_key(user_id: str) -> str:
    return f"user:me:{user_id}"


def batch_key(batch_id: str) -> str:
    return f"batch:{batch_id}"


def predictions_batch_key(batch_id: str) -> str:
    return f"predictions:batch:{batch_id}"


# ---- Interface -----------------------------------------------------------

class CacheInvalidator(Protocol):
    """Anything services need to ask of the cache."""

    async def delete(self, key: str) -> None: ...

    async def delete_many(self, *keys: str) -> None: ...


# ---- In-memory implementation (tests, local dev) -------------------------

class InMemoryCacheInvalidator:
    """No-op-style cache used in tests and before Redis is wired."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def delete_many(self, *keys: str) -> None:
        self.deleted.extend(keys)
