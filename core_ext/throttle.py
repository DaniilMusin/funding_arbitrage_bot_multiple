import os
import time
import asyncio
from redis.asyncio import Redis


class TokenBucket:
    """Simple per-second rate limiter using Redis."""

    def __init__(self, rate: int, redis_url: str | None = None, prefix: str = "token_bucket"):
        self.rate = rate
        self.prefix = prefix
        redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis = Redis.from_url(redis_url, decode_responses=True)

    async def acquire(self, bucket: str = "default") -> None:
        """Acquire one token, waiting if necessary."""
        while True:
            now = int(time.time())
            key = f"{self.prefix}:{bucket}:{now}"
            count = await self.redis.incr(key)
            if count == 1:
                await self.redis.expire(key, 1)
            if count <= self.rate:
                return
            await asyncio.sleep(max(0, 1 - (time.time() - now)))
