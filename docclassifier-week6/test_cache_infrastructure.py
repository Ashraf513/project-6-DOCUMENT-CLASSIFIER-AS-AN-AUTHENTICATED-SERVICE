"""
End‑to‑end test of the caching infrastructure WITH data display.

Requires Redis running on localhost:6379
(e.g., docker run -d --name testredis -p 6379:6379 redis:7-alpine).

1. Populates Redis with dummy data under the same keys fastapi-cache2 uses.
2. Reads and prints every stored value (proof the cache is filled).
3. Runs RedisCacheInvalidator to delete keys.
4. Confirms Redis is empty afterwards.
"""

import asyncio
import json

import redis.asyncio as redis

from app.infra.cache import (
    RedisCacheInvalidator,
    USERS_LIST_KEY,
    BATCHES_LIST_KEY,
    PREDICTIONS_RECENT_KEY,
    user_me_key,
    batch_key,
    predictions_batch_key,
)

# Same Redis URL as docker-compose will use
REDIS_URL = "redis://localhost:6379/0"


# ---------------------------------------------------------------------------
# Helper: populate cache keys with dummy JSON values
# ---------------------------------------------------------------------------
async def populate_cache(client: redis.Redis):
    """Write the same keys fastapi-cache2 would create after HTTP requests."""
    sample_data = {
        user_me_key("u1"):          {"id": "u1", "email": "alice@example.com", "role": "admin", "is_active": True},
        USERS_LIST_KEY:            [{"id": "u1", "email": "alice@example.com"}, {"id": "u2", "email": "bob@example.com"}],
        BATCHES_LIST_KEY:          [{"id": "b1", "status": "done"}, {"id": "b2", "status": "processing"}],
        batch_key("b1"):           {"id": "b1", "status": "done", "predictions": [{"id": "p1"}]},
        PREDICTIONS_RECENT_KEY:    [{"id": "p1", "class": "invoice", "confidence": 0.95}],
        predictions_batch_key("b1"): [{"id": "p1", "class": "invoice"}],
    }

    for key, value in sample_data.items():
        await client.set(key, json.dumps(value))


# ---------------------------------------------------------------------------
# Helper: fetch and display a key's value
# ---------------------------------------------------------------------------
async def show_key(client: redis.Redis, key: str, label: str):
    val = await client.get(key)
    if val is None:
        print(f"  {label} ({key})  →  ❌ MISSING (cache miss)")
    else:
        print(f"  {label} ({key})  →  ✅ PRESENT")
        print(f"      Value: {val.decode('utf-8')}")


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------
async def main():
    # 1. Connect and clean slate
    r = redis.from_url(REDIS_URL)
    await r.flushdb()

    # 2. Populate (simulate API calls that cached responses)
    await populate_cache(r)
    print("📦 Cache populated with dummy data.\n")

    # 3. Show all cached data
    print("=" * 70)
    print(" CURRENT CACHE CONTENTS (data inside Redis)")
    print("=" * 70)
    await show_key(r, user_me_key("u1"),          "/me for u1")
    await show_key(r, USERS_LIST_KEY,            "User list")
    await show_key(r, BATCHES_LIST_KEY,          "Batch list")
    await show_key(r, batch_key("b1"),           "Batch b1 detail")
    await show_key(r, PREDICTIONS_RECENT_KEY,    "Recent predictions")
    await show_key(r, predictions_batch_key("b1"), "Predictions for batch b1")
    print()

    # 4. Instantiate the invalidator
    invalidator = RedisCacheInvalidator(REDIS_URL)

    # 5. Delete one key and show it's gone
    print("=" * 70)
    print(" INVALIDATION TEST: delete single key (user:me:u1)")
    print("=" * 70)
    target = user_me_key("u1")
    print(f"Before deletion: exists? {await r.exists(target) > 0}")
    await invalidator.delete(target)
    print(f"After  deletion: exists? {await r.exists(target) > 0}")
    assert await r.exists(target) == 0, "Key should be deleted"
    print("✅ Single key deletion confirmed\n")

    # 6. Delete multiple keys at once
    print("=" * 70)
    print(" INVALIDATION TEST: delete many keys")
    print("=" * 70)
    batch_keys = [BATCHES_LIST_KEY, batch_key("b1")]
    print("Keys before deletion:")
    for k in batch_keys:
        print(f"  {k}  → exists? {await r.exists(k) > 0}")
    await invalidator.delete_many(*batch_keys)
    print("Keys after deletion:")
    for k in batch_keys:
        print(f"  {k}  → exists? {await r.exists(k) > 0}")
        assert await r.exists(k) == 0, f"{k} should be gone"
    print("✅ Multiple keys deleted\n")

    # 7. Wipe the remaining keys (simulating service operations)
    remaining = [
        USERS_LIST_KEY,
        PREDICTIONS_RECENT_KEY,
        predictions_batch_key("b1"),
    ]
    await invalidator.delete_many(*remaining)
    for k in remaining:
        assert await r.exists(k) == 0

    # 8. Confirm Redis is entirely empty
    all_keys = await r.keys("*")
    assert len(all_keys) == 0, f"Redis should be empty, but got: {all_keys}"
    print("=" * 70)
    print(" FINAL CHECK: Redis is completely empty after invalidation")
    print("=" * 70)
    print("✅ All keys removed, no stale data remains\n")

    await invalidator.close()
    await r.close()
    print("🎉 Cache infrastructure test passed!")


if __name__ == "__main__":
    asyncio.run(main())