"""Redis connection manager for caching, rate limiting, and FSM state."""

import logging

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class RedisManager:
    """Async Redis client wrapper."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: aioredis.Redis | None = None

    async def initialize(self) -> None:
        """Create Redis connection."""
        self.client = aioredis.from_url(
            self.redis_url,
            decode_responses=True,
        )
        await self.client.ping()
        logger.info("Redis connection established")

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        await self.client.setex(key, ttl, value)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def incr(self, key: str) -> int:
        return await self.client.incr(key)

    async def expire(self, key: str, ttl: int) -> None:
        await self.client.expire(key, ttl)

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))
