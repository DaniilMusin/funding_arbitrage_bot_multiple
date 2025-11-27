"""
Enhanced rate limiter with token bucket algorithm per exchange and exponential backoff with jitter.
"""
import asyncio
import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional

from hummingbot.logger import HummingbotLogger


@dataclass
class TokenBucket:
    """Token bucket for rate limiting with configurable capacity and refill rate."""
    capacity: int
    refill_rate: float  # tokens per second
    tokens: float = 0
    last_refill: float = 0

    def __post_init__(self):
        if self.last_refill == 0:
            self.last_refill = time.time()
            self.tokens = self.capacity


class ExponentialBackoff:
    """Exponential backoff with jitter for critical REST calls."""

    def __init__(self,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 multiplier: float = 2.0,
                 jitter_factor: float = 0.1):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter_factor = jitter_factor
        self.attempts = 0

    def get_delay(self) -> float:
        """Calculate delay with exponential backoff and jitter."""
        if self.attempts == 0:
            return 0

        delay = self.base_delay * (self.multiplier ** (self.attempts - 1))
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        jitter = delay * self.jitter_factor * (random.random() - 0.5)
        return max(0, delay + jitter)

    def increment(self):
        """Increment attempt counter."""
        self.attempts += 1

    def reset(self):
        """Reset attempt counter on success."""
        self.attempts = 0


class EnhancedRateLimiter:
    """
    Enhanced rate limiter with token bucket per exchange and exponential backoff.

    Features:
    - Token bucket algorithm for smooth rate limiting
    - Per-exchange rate limiting
    - Exponential backoff with jitter for failed requests
    - Critical request prioritization
    """

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self):
        self._exchange_buckets: Dict[str, TokenBucket] = {}
        self._exchange_backoffs: Dict[str, ExponentialBackoff] = {}
        self._lock = asyncio.Lock()

        # Default configurations
        self._default_capacity = 100
        self._default_refill_rate = 10.0  # tokens per second

        # Exchange-specific configurations
        self._exchange_configs = {
            "binance": {"capacity": 1200, "refill_rate": 20.0},
            "coinbase": {"capacity": 100, "refill_rate": 10.0},
            "kraken": {"capacity": 60, "refill_rate": 1.0},
            "bybit": {"capacity": 600, "refill_rate": 10.0},
            "okx": {"capacity": 300, "refill_rate": 5.0},
        }

    def _get_or_create_bucket(self, exchange: str) -> TokenBucket:
        """Get or create token bucket for exchange."""
        if exchange not in self._exchange_buckets:
            config = self._exchange_configs.get(exchange, {
                "capacity": self._default_capacity,
                "refill_rate": self._default_refill_rate
            })
            self._exchange_buckets[exchange] = TokenBucket(
                capacity=config["capacity"],
                refill_rate=config["refill_rate"]
            )
        return self._exchange_buckets[exchange]

    def _get_or_create_backoff(self, exchange: str) -> ExponentialBackoff:
        """Get or create exponential backoff for exchange."""
        if exchange not in self._exchange_backoffs:
            self._exchange_backoffs[exchange] = ExponentialBackoff()
        return self._exchange_backoffs[exchange]

    def _refill_bucket(self, bucket: TokenBucket):
        """Refill token bucket based on elapsed time."""
        now = time.time()
        elapsed = now - bucket.last_refill
        tokens_to_add = elapsed * bucket.refill_rate
        bucket.tokens = min(bucket.capacity, bucket.tokens + tokens_to_add)
        bucket.last_refill = now

    async def acquire_tokens(self,
                           exchange: str,
                           tokens_needed: int = 1,
                           is_critical: bool = False) -> bool:
        """
        Acquire tokens from the exchange's bucket.

        Args:
            exchange: Exchange name
            tokens_needed: Number of tokens required
            is_critical: Whether this is a critical request (affects backoff)

        Returns:
            True if tokens were acquired, False otherwise
        """
        async with self._lock:
            bucket = self._get_or_create_bucket(exchange)
            backoff = self._get_or_create_backoff(exchange)

            self._refill_bucket(bucket)

            if bucket.tokens >= tokens_needed:
                bucket.tokens -= tokens_needed
                if is_critical:
                    backoff.reset()  # Reset backoff on successful critical request
                return True

            return False

    async def wait_for_tokens(self,
                            exchange: str,
                            tokens_needed: int = 1,
                            is_critical: bool = False,
                            timeout: float = 60.0) -> bool:
        """
        Wait for tokens to become available with exponential backoff.

        Args:
            exchange: Exchange name
            tokens_needed: Number of tokens required
            is_critical: Whether this is a critical request
            timeout: Maximum time to wait

        Returns:
            True if tokens were acquired within timeout, False otherwise
        """
        start_time = time.time()
        backoff = self._get_or_create_backoff(exchange)

        while time.time() - start_time < timeout:
            if await self.acquire_tokens(exchange, tokens_needed, is_critical):
                return True

            # Apply exponential backoff for critical requests
            if is_critical:
                backoff.increment()
                delay = backoff.get_delay()
                if delay > 0:
                    self.logger().debug(
                        f"Rate limited on {exchange}, backing off for {delay:.2f}s "
                        f"(attempt {backoff.attempts})"
                    )
                    await asyncio.sleep(delay)
            else:
                # For non-critical requests, wait for bucket to refill
                bucket = self._get_or_create_bucket(exchange)
                wait_time = tokens_needed / bucket.refill_rate
                await asyncio.sleep(min(wait_time, 1.0))

        self.logger().warning(
            f"Failed to acquire {tokens_needed} tokens for {exchange} within {timeout}s timeout"
        )
        return False

    def get_bucket_status(self, exchange: str) -> Dict:
        """Get current status of exchange's token bucket."""
        bucket = self._get_or_create_bucket(exchange)
        self._refill_bucket(bucket)

        return {
            "exchange": exchange,
            "tokens_available": bucket.tokens,
            "capacity": bucket.capacity,
            "refill_rate": bucket.refill_rate,
            "utilization": 1.0 - (bucket.tokens / bucket.capacity)
        }

    def get_all_statuses(self) -> Dict[str, Dict]:
        """Get status of all exchange token buckets."""
        return {
            exchange: self.get_bucket_status(exchange)
            for exchange in self._exchange_buckets.keys()
        }

    def configure_exchange(self,
                          exchange: str,
                          capacity: int,
                          refill_rate: float):
        """Configure rate limits for specific exchange."""
        self._exchange_configs[exchange] = {
            "capacity": capacity,
            "refill_rate": refill_rate
        }

        # Update existing bucket if it exists
        if exchange in self._exchange_buckets:
            bucket = self._exchange_buckets[exchange]
            bucket.capacity = capacity
            bucket.refill_rate = refill_rate
            bucket.tokens = min(bucket.tokens, capacity)