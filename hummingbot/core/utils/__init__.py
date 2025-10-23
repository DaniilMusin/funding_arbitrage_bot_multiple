def trade_guard(func):
    """Decorator to enforce readiness guard and circuit breakers before placing orders.

    It expects the wrapped function to receive connector_name and trading_pair as named args or positions.
    """
    from functools import wraps
    from hummingbot.core.reliability import get_reliability_manager
    from hummingbot.core.observability.metrics import get_metrics_collector

    @wraps(func)
    def wrapper(*args, **kwargs):
        connector_name = kwargs.get('connector_name')
        trading_pair = kwargs.get('trading_pair')
        # Fallback best-effort for positional
        if connector_name is None and len(args) >= 2:
            connector_name = args[0] if isinstance(args[0], str) else kwargs.get('connector_name', 'unknown')
            trading_pair = args[1] if isinstance(args[1], str) else kwargs.get('trading_pair', 'unknown')

        rm = get_reliability_manager()
        can, reason = rm.can_trade()
        if not can:
            get_metrics_collector().record_trading_block(reason=reason, exchange=connector_name or 'unknown', trading_pair=trading_pair or 'unknown')
            raise RuntimeError(f"Trade blocked: {reason}")
        return func(*args, **kwargs)
    return wrapper

import errno
import functools
import socket

import cachetools
import numpy as np
import pandas as pd


def async_ttl_cache(ttl: int = 3600, maxsize: int = 1):
    cache = cachetools.TTLCache(ttl=ttl, maxsize=maxsize)

    def decorator(fn):
        @functools.wraps(fn)
        async def memoize(*args, **kwargs):
            key = str((args, kwargs))
            try:
                return cache[key]
            except KeyError:
                cache[key] = await fn(*args, **kwargs)
                return cache[key]

        memoize.cache_clear = lambda: cache.clear()
        return memoize

    return decorator


def map_df_to_str(df: pd.DataFrame) -> pd.DataFrame:
    return df.apply(lambda series: series.map(lambda x: np.format_float_positional(x, trim="-") if isinstance(x, float) else x)).astype(str)


def detect_available_port(starting_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        current_port: int = starting_port
        while current_port < 65535:
            try:
                s.bind(("127.0.0.1", current_port))
                break
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    current_port += 1
                    continue
        return current_port
