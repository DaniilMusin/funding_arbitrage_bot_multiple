import os
import time
import asyncio
import logging
from redis.asyncio import Redis


class TokenBucket:
    """Simple per-second rate limiter using Redis.

    Implements async context manager for proper resource cleanup.
    Includes timeout protection to prevent infinite loops.
    """

    def __init__(self, rate: int, redis_url: str | None = None, prefix: str = "token_bucket", acquire_timeout: int = 30):
        self.rate = rate
        self.prefix = prefix
        self.acquire_timeout = acquire_timeout  # Maximum time to wait for token acquisition
        self.logger = logging.getLogger(__name__)
        redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self._closed = False

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures Redis connection cleanup."""
        await self.close()
        return False

    async def close(self):
        """Close Redis connection to prevent resource leak."""
        if not self._closed:
            try:
                await self.redis.close()
                self._closed = True
            except Exception as e:
                self.logger.error(f"Error closing Redis connection: {e}")

    async def acquire(self, bucket: str = "default") -> None:
        """Acquire one token, waiting if necessary.

        Args:
            bucket: Bucket name for rate limiting

        Raises:
            TimeoutError: If token cannot be acquired within acquire_timeout seconds
            ConnectionError: If Redis connection fails
        """
        if self._closed:
            raise RuntimeError("TokenBucket is closed")

        start_time = time.time()

        while True:
            # Check timeout to prevent infinite loop
            elapsed = time.time() - start_time
            if elapsed > self.acquire_timeout:
                raise TimeoutError(
                    f"Failed to acquire token within {self.acquire_timeout} seconds. "
                    f"Rate limit: {self.rate}/sec, bucket: {bucket}"
                )

            try:
                now = int(time.time())
                key = f"{self.prefix}:{bucket}:{now}"
                count = await self.redis.incr(key)
                if count == 1:
                    await self.redis.expire(key, 1)
                if count <= self.rate:
                    return
                await asyncio.sleep(max(0, 1 - (time.time() - now)))
            except Exception as e:
                self.logger.error(f"Redis error during token acquisition: {e}")
                raise ConnectionError(f"Redis connection failed: {e}") from e
