"""
Rate Limiter for API calls
Prevents IP bans from exchanges by limiting request rate
"""
import time
import logging
from typing import Dict, Optional
from threading import Lock
from collections import deque
from functools import wraps


class RateLimiter:
    """
    Rate limiter for API calls to prevent IP bans.

    Uses token bucket algorithm with per-exchange limits.
    """

    def __init__(self):
        """Initialize rate limiter with exchange-specific limits"""
        self.logger = logging.getLogger(__name__)

        # Exchange-specific rate limits (calls per second)
        # Conservative limits to stay well below official limits
        self.exchange_limits = {
            "okx_perpetual": 10,          # OKX: 20/sec official, use 10 for safety
            "hyperliquid_perpetual": 20,  # Hyperliquid: higher limit
            "binance_perpetual": 10,      # Binance: 1200/min = 20/sec, use 10
            "bybit_perpetual": 10,        # Bybit: 120/min = 2/sec, use conservative
            "gate_io_perpetual": 5,       # Gate.io: lower limit
            "kucoin_perpetual": 5,        # KuCoin: conservative
            "bingx_perpetual": 5,         # BingX: conservative
            "bitget_perpetual": 10,       # Bitget: moderate
            "mexc_perpetual": 5,          # MEXC: conservative
            "phemex_perpetual": 10,       # Phemex: moderate
        }

        # Default limit for unknown exchanges
        self.default_limit = 5

        # Track request timestamps per exchange
        self.request_history: Dict[str, deque] = {}
        self.locks: Dict[str, Lock] = {}

        # Initialize tracking for each exchange
        for exchange in self.exchange_limits.keys():
            self.request_history[exchange] = deque()
            self.locks[exchange] = Lock()

        self.logger.info(f"Rate limiter initialized with {len(self.exchange_limits)} exchange limits")

    def _get_limit(self, exchange: str) -> int:
        """Get rate limit for exchange"""
        return self.exchange_limits.get(exchange, self.default_limit)

    def _cleanup_old_requests(self, exchange: str, current_time: float, window: float):
        """Remove requests older than time window"""
        history = self.request_history[exchange]
        while history and history[0] < current_time - window:
            history.popleft()

    def wait_if_needed(self, exchange: str) -> float:
        """
        Wait if rate limit would be exceeded.

        Args:
            exchange: Exchange name (e.g., "okx_perpetual")

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        # Get or create tracking for this exchange
        if exchange not in self.request_history:
            self.request_history[exchange] = deque()
            self.locks[exchange] = Lock()

        limit = self._get_limit(exchange)
        window = 1.0  # 1 second window
        wait_time = 0.0

        with self.locks[exchange]:
            current_time = time.time()

            # Clean up old requests
            self._cleanup_old_requests(exchange, current_time, window)

            # Check if we've hit the limit
            if len(self.request_history[exchange]) >= limit:
                # Calculate wait time
                oldest_request = self.request_history[exchange][0]
                wait_time = oldest_request + window - current_time

                if wait_time > 0:
                    self.logger.debug(f"Rate limit reached for {exchange}: waiting {wait_time:.3f}s")
                    time.sleep(wait_time)
                    current_time = time.time()

                    # Clean up again after waiting
                    self._cleanup_old_requests(exchange, current_time, window)

            # Record this request
            self.request_history[exchange].append(current_time)

            return wait_time if wait_time > 0 else 0.0

    def get_stats(self, exchange: str) -> dict:
        """Get rate limiting statistics for exchange"""
        if exchange not in self.request_history:
            return {
                "exchange": exchange,
                "requests_last_second": 0,
                "limit": self._get_limit(exchange),
                "utilization": 0.0
            }

        with self.locks[exchange]:
            current_time = time.time()
            self._cleanup_old_requests(exchange, current_time, 1.0)

            requests_count = len(self.request_history[exchange])
            limit = self._get_limit(exchange)

            return {
                "exchange": exchange,
                "requests_last_second": requests_count,
                "limit": limit,
                "utilization": (requests_count / limit) * 100 if limit > 0 else 0
            }

    def get_all_stats(self) -> list:
        """Get statistics for all tracked exchanges"""
        stats = []
        for exchange in self.request_history.keys():
            stats.append(self.get_stats(exchange))
        return stats


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance (singleton)"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def rate_limited(exchange_param: str = "connector_name"):
    """
    Decorator to rate limit function calls.

    Args:
        exchange_param: Name of parameter containing exchange name

    Usage:
        @rate_limited("connector_name")
        def safe_get_price(self, connector_name: str, ...):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get exchange name from parameters
            # Try to get from kwargs first
            exchange = kwargs.get(exchange_param)

            # If not in kwargs, try to get from args
            if exchange is None:
                # Get function signature to find parameter index
                import inspect
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())

                if exchange_param in param_names:
                    param_index = param_names.index(exchange_param)
                    if param_index < len(args):
                        exchange = args[param_index]

            # Apply rate limiting if exchange found
            if exchange:
                limiter = get_rate_limiter()
                limiter.wait_if_needed(exchange)

            # Call original function
            return func(*args, **kwargs)

        return wrapper
    return decorator


# Example usage and testing
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    limiter = RateLimiter()

    print("Testing rate limiter...")
    print(f"OKX limit: {limiter._get_limit('okx_perpetual')} req/sec")
    print(f"Hyperliquid limit: {limiter._get_limit('hyperliquid_perpetual')} req/sec")

    # Test 1: Normal requests within limit
    print("\nTest 1: Normal requests (should not wait)")
    for i in range(5):
        wait_time = limiter.wait_if_needed("okx_perpetual")
        print(f"  Request {i+1}: waited {wait_time:.3f}s")

    # Test 2: Exceed limit
    print("\nTest 2: Exceeding limit (should wait)")
    for i in range(15):
        start = time.time()
        limiter.wait_if_needed("okx_perpetual")
        elapsed = time.time() - start
        print(f"  Request {i+1}: waited {elapsed:.3f}s")

    # Test 3: Statistics
    print("\nTest 3: Statistics")
    stats = limiter.get_stats("okx_perpetual")
    print(f"  Exchange: {stats['exchange']}")
    print(f"  Requests/sec: {stats['requests_last_second']}/{stats['limit']}")
    print(f"  Utilization: {stats['utilization']:.1f}%")

    # Test 4: Decorator
    print("\nTest 4: Decorator usage")

    @rate_limited("exchange")
    def test_api_call(exchange: str):
        print(f"  API call to {exchange}")
        return "success"

    for i in range(12):
        result = test_api_call("okx_perpetual")

    print("\n✅ Rate limiter tests completed!")
