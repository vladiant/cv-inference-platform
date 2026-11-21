"""@file
@brief Concrete ResultCache adapter backed by Redis (string GET/SET + TTL).
"""
from typing import Optional
import redis.asyncio as redis


class RedisResultCache:
    def __init__(self, redis_url: str):
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        """@brief Return the cached value for ``key`` or None on a miss."""
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """@brief Cache ``value`` under ``key`` with a TTL in seconds."""
        await self._redis.set(key, value, ex=ttl_seconds)

    async def close(self) -> None:
        """@brief Release the Redis connection on service shutdown."""
        await self._redis.aclose()
