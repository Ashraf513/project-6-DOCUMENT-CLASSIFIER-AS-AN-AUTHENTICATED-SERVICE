"""
Smoke test for RedisCacheInvalidator.

Run after starting a Redis container on localhost:6379.
"""

import asyncio
from app.infra.cache import RedisCacheInvalidator


async def main():
    # Connect to the standalone Redis
    cache = RedisCacheInvalidator("redis://localhost:6379/0")

    # Delete some keys
    await cache.delete("test:key1")
    await cache.delete("test:key2")

    # Delete many
    await cache.delete_many("test:key1", "test:key2", "nonexistent")

    print("✅ RedisCacheInvalidator worked – no exceptions")

    await cache.close()

if __name__ == "__main__":
    asyncio.run(main())