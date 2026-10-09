"""Concrete EventPublisher adapter backed by a Redis Stream.

MAXLEN keeps the stream self-trimming once consumer groups have
acknowledged old entries — see docs/design-decisions.md.
"""
import json
import redis.asyncio as redis


class RedisEventPublisher:
    def __init__(self, redis_url: str, maxlen: int = 100_000):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._maxlen = maxlen

    async def publish(self, stream: str, payload: dict) -> None:
        await self._redis.xadd(
            stream,
            {"data": json.dumps(payload)},
            maxlen=self._maxlen,
            approximate=True,
        )

    async def close(self) -> None:
        await self._redis.aclose()
