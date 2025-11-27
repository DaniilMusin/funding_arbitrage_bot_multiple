"""
Observability module for Hummingbot trading system.

This module provides comprehensive observability features including:
- Structured logging with JSON format and correlation IDs
- Prometheus metrics for monitoring system performance
- Alerting system with rate limiting and deduplication
"""

from .metrics import (
    MetricsCollector,
    ErrorType,
    get_metrics_collector,
    time_rest_request
)

from .alerting import (
    Alert,
    AlertSeverity,
    AlertChannel,
    AlertManager,
    RateLimitConfig,
    get_alert_manager,
    send_alert
)

from .integration import (
    ObservabilityManager,
    get_observability_manager,
    setup_observability,
    log_exchange_operation,
    log_trading_operation
)

__all__ = [
    # Metrics
    'MetricsCollector',
    'ErrorType',
    'get_metrics_collector',
    'time_rest_request',

    # Alerting
    'Alert',
    'AlertSeverity',
    'AlertChannel',
    'AlertManager',
    'RateLimitConfig',
    'get_alert_manager',
    'send_alert',

    # Integration
    'ObservabilityManager',
    'get_observability_manager',
    'setup_observability',
    'log_exchange_operation',
    'log_trading_operation',
]