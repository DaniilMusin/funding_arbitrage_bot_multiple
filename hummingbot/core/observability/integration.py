"""
Observability integration module for easy setup and configuration.
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any

from hummingbot.logger.observability_logger import (
    get_observability_logger,
    ObservabilityLogger,
    new_correlation_id
)
from hummingbot.core.observability.metrics import get_metrics_collector, MetricsCollector
from hummingbot.core.observability.alerting import (
    get_alert_manager,
    AlertManager,
    RateLimitConfig,
    AlertSeverity,
    send_alert
)


class ObservabilityManager:
    """Central manager for all observability features."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize observability manager."""
        self.config = config or {}

        # Initialize components
        self.logger = get_observability_logger(__name__)
        self.metrics = get_metrics_collector()

        # Configure rate limiting
        rate_limit_config = RateLimitConfig(
            max_alerts_per_minute=self.config.get('max_alerts_per_minute', 5),
            max_alerts_per_hour=self.config.get('max_alerts_per_hour', 20),
            max_alerts_per_day=self.config.get('max_alerts_per_day', 100),
            dedup_window_seconds=self.config.get('dedup_window_seconds', 3600),
        )

        self.alerts = AlertManager(rate_limit_config)

        # Configure logging
        self._setup_logging()

        self.logger.info_structured(
            "Observability manager initialized",
            config=self.config
        )

    def _setup_logging(self):
        """Setup structured logging configuration."""
        # Configure log level from environment
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        numeric_level = getattr(logging, log_level, logging.INFO)

        # Set level for all hummingbot loggers
        logging.getLogger('hummingbot').setLevel(numeric_level)

        # Configure JSON formatter if requested
        if os.getenv('JSON_LOGGING', '').lower() in ('true', '1', 'yes'):
            self._setup_json_logging()

    def _setup_json_logging(self):
        """Setup JSON structured logging for all handlers."""
        import json
        from logging import Formatter

        class JSONFormatter(Formatter):
            def format(self, record):
                # Use the enhanced log record format if available
                if hasattr(record, 'getMessage') and hasattr(record.__class__, '__name__'):
                    if 'ObservabilityLogRecord' in record.__class__.__name__:
                        return record.getMessage()

                # Fall back to basic JSON formatting
                log_data = {
                    'timestamp': record.created,
                    'level': record.levelname,
                    'logger': record.name,
                    'message': record.getMessage(),
                    'module': record.module,
                    'function': record.funcName,
                    'line': record.lineno,
                }
                return json.dumps(log_data, separators=(',', ':'))

        # Apply to all handlers
        for handler in logging.getLogger().handlers:
            handler.setFormatter(JSONFormatter())

    async def setup_health_endpoint_integration(self, health_endpoint):
        """Integrate with health endpoint for metrics exposure."""
        if hasattr(health_endpoint, 'set_dependencies'):
            # Register metrics collector as a dependency
            health_endpoint.register_component('metrics_collector', self.metrics)

    def get_logger(self, name: str) -> ObservabilityLogger:
        """Get an observability logger for the given name."""
        return get_observability_logger(name)

    def record_exchange_operation(self,
                                exchange: str,
                                operation: str,
                                duration: Optional[float] = None,
                                success: bool = True,
                                error_type: Optional[str] = None):
        """Record metrics for exchange operations."""
        correlation_id = new_correlation_id()

        with self.get_logger(f"exchange.{exchange}").with_correlation_id(correlation_id):
            if duration is not None:
                # Record latency
                if operation.startswith('rest_'):
                    endpoint = operation.replace('rest_', '')
                    self.metrics.record_rest_request(exchange, endpoint, 'GET', duration)
                elif operation.startswith('ws_'):
                    stream_type = operation.replace('ws_', '')
                    self.metrics.record_ws_latency(exchange, stream_type, duration)

            # Record errors
            if not success and error_type:
                from hummingbot.core.observability.metrics import ErrorType
                try:
                    error_enum = ErrorType(error_type.lower())
                except ValueError:
                    error_enum = ErrorType.UNKNOWN_ERROR

                self.metrics.record_error(exchange, error_enum, operation)

                # Send alert for critical errors
                if error_enum in [ErrorType.AUTH_ERROR, ErrorType.RATE_LIMIT_ERROR]:
                    asyncio.create_task(send_alert(
                        title=f"Exchange Error: {exchange}",
                        message=f"Error in {operation}: {error_type}",
                        severity=AlertSeverity.HIGH,
                        component="exchange",
                        exchange=exchange,
                        error_type=error_type
                    ))

    def record_trading_operation(self,
                               exchange: str,
                               trading_pair: str,
                               operation: str,
                               **kwargs):
        """Record metrics for trading operations."""
        correlation_id = new_correlation_id()

        with self.get_logger(f"trading.{exchange}").with_correlation_id(correlation_id):
            with self.get_logger(f"trading.{exchange}").with_exchange_context(exchange, trading_pair):
                if operation == 'order_created':
                    self.metrics.record_order_created(
                        exchange, trading_pair,
                        kwargs.get('side', 'unknown'),
                        kwargs.get('order_type', 'unknown')
                    )
                elif operation == 'order_filled':
                    self.metrics.record_order_filled(
                        exchange, trading_pair,
                        kwargs.get('side', 'unknown'),
                        kwargs.get('fill_latency')
                    )
                elif operation == 'order_cancelled':
                    self.metrics.record_order_cancelled(
                        exchange, trading_pair,
                        kwargs.get('side', 'unknown'),
                        kwargs.get('reason', 'unknown')
                    )
                elif operation == 'commission_paid':
                    self.metrics.record_commission(
                        exchange, trading_pair,
                        kwargs.get('side', 'unknown'),
                        kwargs.get('amount', 0.0)
                    )
                elif operation == 'hedge_slippage':
                    self.metrics.record_hedge_slippage(
                        exchange, trading_pair,
                        kwargs.get('side', 'unknown'),
                        kwargs.get('slippage_bps', 0.0)
                    )

    def update_portfolio_metrics(self, exchange: str, portfolio_data: Dict[str, Any]):
        """Update portfolio-related metrics."""
        if 'total_value_usd' in portfolio_data:
            self.metrics.set_portfolio_value(exchange, portfolio_data['total_value_usd'])

        if 'positions' in portfolio_data:
            for position in portfolio_data['positions']:
                self.metrics.set_position_size(
                    exchange,
                    position.get('trading_pair', 'unknown'),
                    position.get('side', 'unknown'),
                    position.get('size', 0.0)
                )

        if 'unrealized_pnl' in portfolio_data:
            for trading_pair, pnl in portfolio_data['unrealized_pnl'].items():
                self.metrics.set_unrealized_pnl(exchange, trading_pair, pnl)

    def update_funding_metrics(self,
                             exchange: str,
                             trading_pair: str,
                             expected_funding: float,
                             captured_funding: Optional[float] = None):
        """Update funding-related metrics."""
        self.metrics.set_funding_expected(exchange, trading_pair, expected_funding)

        if captured_funding is not None:
            self.metrics.set_funding_captured(exchange, trading_pair, 'actual', captured_funding)

    def set_trading_readiness(self, component: str, is_ready: bool):
        """Update trading readiness metrics."""
        self.metrics.set_trading_readiness(component, is_ready)

        if not is_ready:
            # Send alert for readiness issues
            import asyncio
            asyncio.create_task(send_alert(
                title=f"Trading Readiness Issue: {component}",
                message=f"Component {component} is not ready for trading",
                severity=AlertSeverity.MEDIUM,
                component="trading_readiness",
                metadata={'component': component}
            ))

    async def send_custom_alert(self,
                              title: str,
                              message: str,
                              severity: AlertSeverity,
                              component: str,
                              **kwargs):
        """Send a custom alert."""
        return await send_alert(title, message, severity, component, **kwargs)


# Global observability manager
_observability_manager: Optional[ObservabilityManager] = None


def get_observability_manager(config: Optional[Dict[str, Any]] = None) -> ObservabilityManager:
    """Get the global observability manager."""
    global _observability_manager
    if _observability_manager is None:
        _observability_manager = ObservabilityManager(config)
    return _observability_manager


def setup_observability(config: Optional[Dict[str, Any]] = None) -> ObservabilityManager:
    """Setup observability with the given configuration."""
    return get_observability_manager(config)


# Convenience functions for common operations
def log_exchange_operation(exchange: str, operation: str, **kwargs):
    """Log an exchange operation with structured data."""
    manager = get_observability_manager()
    manager.record_exchange_operation(exchange, operation, **kwargs)


def log_trading_operation(exchange: str, trading_pair: str, operation: str, **kwargs):
    """Log a trading operation with structured data."""
    manager = get_observability_manager()
    manager.record_trading_operation(exchange, trading_pair, operation, **kwargs)