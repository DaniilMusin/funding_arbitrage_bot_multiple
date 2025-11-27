"""
Enhanced structured logging for observability with JSON format and correlation IDs.
"""
import json
import logging
import os
import threading
import time
import uuid
from contextvars import ContextVar
from typing import Dict, Any, Optional

from hummingbot.logger import HummingbotLogger, log_encoder

# Context variable for correlation ID - persists across async calls
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

# Thread-local storage for synchronous contexts
_thread_local = threading.local()


class ObservabilityLogRecord(logging.LogRecord):
    """Enhanced log record with structured data and correlation ID."""

    def getMessage(self):
        """Return structured JSON message with correlation ID and metadata."""
        # Build structured log entry
        log_data = {
            "timestamp": time.time(),
            "level": self.levelname,
            "logger": self.name,
            "message": super().getMessage(),
            "module": self.module,
            "function": self.funcName,
            "line": self.lineno,
        }

        # Add correlation ID from context or thread-local
        correlation_id = self._get_correlation_id()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add exchange context if available
        if hasattr(self, 'exchange'):
            log_data["exchange"] = self.exchange

        # Add trading pair context if available
        if hasattr(self, 'trading_pair'):
            log_data["trading_pair"] = self.trading_pair

        # Add custom structured data if present
        if hasattr(self, 'extra_data') and isinstance(self.extra_data, dict):
            log_data.update(self.extra_data)

        # Add any dict_msg for backwards compatibility
        if hasattr(self, 'dict_msg') and isinstance(self.dict_msg, dict):
            log_data.update(self.dict_msg)

        return json.dumps(log_data, default=log_encoder, separators=(',', ':'))

    def _get_correlation_id(self) -> Optional[str]:
        """Get correlation ID from context or thread-local storage."""
        # Try context variable first (for async contexts)
        try:
            correlation_id = correlation_id_var.get()
            if correlation_id:
                return correlation_id
        except LookupError:
            pass

        # Fall back to thread-local storage
        return getattr(_thread_local, 'correlation_id', None)


class ObservabilityLogger(HummingbotLogger):
    """Enhanced logger with observability features."""

    def __init__(self, name: str):
        super().__init__(name)

        # Override the log record factory
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            # Convert to our enhanced record type
            record.__class__ = ObservabilityLogRecord
            return record

        logging.setLogRecordFactory(record_factory)

        # Configure log level from environment
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        numeric_level = getattr(logging, log_level, logging.INFO)
        self.setLevel(numeric_level)

    def with_correlation_id(self, correlation_id: str = None) -> 'CorrelationContext':
        """Create a context manager that sets correlation ID for all logs."""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        return CorrelationContext(correlation_id)

    def with_exchange_context(self, exchange: str, trading_pair: str = None) -> 'ExchangeContext':
        """Create a context manager that adds exchange context to logs."""
        return ExchangeContext(exchange, trading_pair)

    def structured_log(self, level: int, message: str, extra_data: Dict[str, Any] = None, **kwargs):
        """Log with structured data."""
        if extra_data is None:
            extra_data = {}

        # Add any additional kwargs to extra_data
        extra_data.update(kwargs)

        # Create log record with extra data
        extra = kwargs.get('extra', {})
        extra['extra_data'] = extra_data
        kwargs['extra'] = extra

        self.log(level, message, **kwargs)

    def info_structured(self, message: str, **kwargs):
        """Log info level with structured data."""
        self.structured_log(logging.INFO, message, **kwargs)

    def error_structured(self, message: str, **kwargs):
        """Log error level with structured data."""
        self.structured_log(logging.ERROR, message, **kwargs)

    def warning_structured(self, message: str, **kwargs):
        """Log warning level with structured data."""
        self.structured_log(logging.WARNING, message, **kwargs)

    def debug_structured(self, message: str, **kwargs):
        """Log debug level with structured data."""
        self.structured_log(logging.DEBUG, message, **kwargs)


class CorrelationContext:
    """Context manager for setting correlation ID."""

    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id
        self._token = None

    def __enter__(self):
        # Set in context variable for async contexts
        self._token = correlation_id_var.set(self.correlation_id)

        # Set in thread-local for sync contexts
        _thread_local.correlation_id = self.correlation_id

        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Reset context variable
        if self._token:
            correlation_id_var.reset(self._token)

        # Clear thread-local
        if hasattr(_thread_local, 'correlation_id'):
            delattr(_thread_local, 'correlation_id')


class ExchangeContext:
    """Context manager for setting exchange context."""

    def __init__(self, exchange: str, trading_pair: str = None):
        self.exchange = exchange
        self.trading_pair = trading_pair
        self._old_exchange = None
        self._old_trading_pair = None

    def __enter__(self):
        # Store old values
        self._old_exchange = getattr(_thread_local, 'exchange', None)
        self._old_trading_pair = getattr(_thread_local, 'trading_pair', None)

        # Set new values
        _thread_local.exchange = self.exchange
        if self.trading_pair:
            _thread_local.trading_pair = self.trading_pair

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore old values
        if self._old_exchange is not None:
            _thread_local.exchange = self._old_exchange
        elif hasattr(_thread_local, 'exchange'):
            delattr(_thread_local, 'exchange')

        if self._old_trading_pair is not None:
            _thread_local.trading_pair = self._old_trading_pair
        elif hasattr(_thread_local, 'trading_pair'):
            delattr(_thread_local, 'trading_pair')


def get_observability_logger(name: str) -> ObservabilityLogger:
    """Get or create an observability logger."""
    logger = logging.getLogger(name)
    if not isinstance(logger, ObservabilityLogger):
        logger.__class__ = ObservabilityLogger
        logger.__init__(name)
    return logger


# Convenience function to create correlation ID for new operations
def new_correlation_id() -> str:
    """Generate a new correlation ID."""
    return str(uuid.uuid4())


# Convenience function to get current correlation ID
def get_current_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context."""
    try:
        return correlation_id_var.get()
    except LookupError:
        return getattr(_thread_local, 'correlation_id', None)