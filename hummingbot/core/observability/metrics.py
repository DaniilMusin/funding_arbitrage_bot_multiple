"""
Prometheus metrics for trading system observability.
"""
import time
from typing import Dict, Optional, List
from enum import Enum

from prometheus_client import (
    Counter, Histogram, Gauge, Info, CollectorRegistry, 
    CONTENT_TYPE_LATEST, generate_latest
)


class ErrorType(Enum):
    """Error type classification for metrics."""
    NETWORK_ERROR = "network"
    API_ERROR = "api"
    AUTH_ERROR = "auth"
    RATE_LIMIT_ERROR = "rate_limit"
    PARSE_ERROR = "parse"
    VALIDATION_ERROR = "validation"
    UNKNOWN_ERROR = "unknown"


class MetricsCollector:
    """Centralized metrics collection for the trading system."""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """Initialize metrics collector."""
        self.registry = registry or CollectorRegistry()
        
        # System info
        self.system_info = Info(
            'hummingbot_system_info',
            'System information',
            registry=self.registry
        )
        
        # REST API latency
        self.rest_latency = Histogram(
            'hummingbot_rest_request_duration_seconds',
            'REST API request duration in seconds',
            ['exchange', 'endpoint', 'method'],
            registry=self.registry,
            buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
        )
        
        # WebSocket metrics
        self.ws_reconnects = Counter(
            'hummingbot_websocket_reconnects_total',
            'Total WebSocket reconnections',
            ['exchange', 'stream_type'],
            registry=self.registry
        )
        
        self.ws_latency = Histogram(
            'hummingbot_websocket_message_delay_seconds',
            'WebSocket message processing delay',
            ['exchange', 'stream_type'],
            registry=self.registry,
            buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0)
        )
        
        # Funding metrics
        self.funding_captured = Gauge(
            'hummingbot_funding_captured_total',
            'Total funding captured',
            ['exchange', 'trading_pair', 'type'],
            registry=self.registry
        )
        
        self.funding_expected = Gauge(
            'hummingbot_funding_expected_total',
            'Expected funding amount',
            ['exchange', 'trading_pair'],
            registry=self.registry
        )
        
        # Commission metrics
        self.commissions_paid = Counter(
            'hummingbot_commissions_paid_total',
            'Total commissions paid',
            ['exchange', 'trading_pair', 'side'],
            registry=self.registry
        )
        
        # Hedge slippage
        self.hedge_slippage = Histogram(
            'hummingbot_hedge_slippage_bps',
            'Hedge execution slippage in basis points',
            ['exchange', 'trading_pair', 'side'],
            registry=self.registry,
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0)
        )
        
        # Error rates
        self.errors_total = Counter(
            'hummingbot_errors_total',
            'Total errors by type',
            ['exchange', 'error_type', 'component'],
            registry=self.registry
        )
        
        # Order metrics
        self.orders_created = Counter(
            'hummingbot_orders_created_total',
            'Total orders created',
            ['exchange', 'trading_pair', 'side', 'order_type'],
            registry=self.registry
        )
        
        self.orders_filled = Counter(
            'hummingbot_orders_filled_total',
            'Total orders filled',
            ['exchange', 'trading_pair', 'side'],
            registry=self.registry
        )
        
        self.orders_cancelled = Counter(
            'hummingbot_orders_cancelled_total',
            'Total orders cancelled',
            ['exchange', 'trading_pair', 'side', 'reason'],
            registry=self.registry
        )
        
        self.order_fill_latency = Histogram(
            'hummingbot_order_fill_latency_seconds',
            'Time from order creation to fill',
            ['exchange', 'trading_pair', 'side'],
            registry=self.registry,
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0)
        )
        
        # Trading readiness SLA
        self.trading_readiness = Gauge(
            'hummingbot_trading_readiness',
            'Trading readiness status (1=ready, 0=not ready)',
            ['component'],
            registry=self.registry
        )
        
        self.readiness_uptime = Counter(
            'hummingbot_readiness_uptime_seconds_total',
            'Total uptime in ready state',
            ['component'],
            registry=self.registry
        )
        
        # Portfolio metrics
        self.portfolio_value = Gauge(
            'hummingbot_portfolio_value_usd',
            'Total portfolio value in USD',
            ['exchange'],
            registry=self.registry
        )
        
        self.position_size = Gauge(
            'hummingbot_position_size',
            'Current position size',
            ['exchange', 'trading_pair', 'side'],
            registry=self.registry
        )
        
        # Performance metrics
        self.pnl_realized = Counter(
            'hummingbot_pnl_realized_usd_total',
            'Realized PnL in USD',
            ['exchange', 'trading_pair'],
            registry=self.registry
        )
        
        self.pnl_unrealized = Gauge(
            'hummingbot_pnl_unrealized_usd',
            'Unrealized PnL in USD',
            ['exchange', 'trading_pair'],
            registry=self.registry
        )
        
        # Initialize system info
        self._update_system_info()
    
    def _update_system_info(self):
        """Update system information metrics."""
        import hummingbot
        self.system_info.info({
            'version': getattr(hummingbot, '__version__', 'unknown'),
            'python_version': f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
            'start_time': str(int(time.time()))
        })
    
    # REST API metrics
    def record_rest_request(self, exchange: str, endpoint: str, method: str, duration: float):
        """Record REST API request metrics."""
        self.rest_latency.labels(exchange=exchange, endpoint=endpoint, method=method).observe(duration)
    
    # WebSocket metrics
    def record_ws_reconnect(self, exchange: str, stream_type: str):
        """Record WebSocket reconnection."""
        self.ws_reconnects.labels(exchange=exchange, stream_type=stream_type).inc()
    
    def record_ws_latency(self, exchange: str, stream_type: str, delay: float):
        """Record WebSocket message processing delay."""
        self.ws_latency.labels(exchange=exchange, stream_type=stream_type).observe(delay)
    
    # Funding metrics
    def set_funding_captured(self, exchange: str, trading_pair: str, funding_type: str, amount: float):
        """Set funding captured amount."""
        self.funding_captured.labels(exchange=exchange, trading_pair=trading_pair, type=funding_type).set(amount)
    
    def set_funding_expected(self, exchange: str, trading_pair: str, amount: float):
        """Set expected funding amount."""
        self.funding_expected.labels(exchange=exchange, trading_pair=trading_pair).set(amount)
    
    # Commission metrics
    def record_commission(self, exchange: str, trading_pair: str, side: str, amount: float):
        """Record commission paid."""
        self.commissions_paid.labels(exchange=exchange, trading_pair=trading_pair, side=side).inc(amount)
    
    # Hedge slippage
    def record_hedge_slippage(self, exchange: str, trading_pair: str, side: str, slippage_bps: float):
        """Record hedge execution slippage."""
        self.hedge_slippage.labels(exchange=exchange, trading_pair=trading_pair, side=side).observe(slippage_bps)
    
    # Error metrics
    def record_error(self, exchange: str, error_type: ErrorType, component: str):
        """Record an error occurrence."""
        self.errors_total.labels(
            exchange=exchange, 
            error_type=error_type.value, 
            component=component
        ).inc()
    
    # Order metrics
    def record_order_created(self, exchange: str, trading_pair: str, side: str, order_type: str):
        """Record order creation."""
        self.orders_created.labels(
            exchange=exchange, 
            trading_pair=trading_pair, 
            side=side, 
            order_type=order_type
        ).inc()
    
    def record_order_filled(self, exchange: str, trading_pair: str, side: str, fill_latency: float = None):
        """Record order fill."""
        self.orders_filled.labels(exchange=exchange, trading_pair=trading_pair, side=side).inc()
        
        if fill_latency is not None:
            self.order_fill_latency.labels(
                exchange=exchange, 
                trading_pair=trading_pair, 
                side=side
            ).observe(fill_latency)
    
    def record_order_cancelled(self, exchange: str, trading_pair: str, side: str, reason: str):
        """Record order cancellation."""
        self.orders_cancelled.labels(
            exchange=exchange, 
            trading_pair=trading_pair, 
            side=side, 
            reason=reason
        ).inc()
    
    # Trading readiness SLA
    def set_trading_readiness(self, component: str, is_ready: bool):
        """Set trading readiness status."""
        self.trading_readiness.labels(component=component).set(1 if is_ready else 0)
    
    def record_readiness_uptime(self, component: str, uptime_seconds: float):
        """Record uptime in ready state."""
        self.readiness_uptime.labels(component=component).inc(uptime_seconds)
    
    # Portfolio metrics
    def set_portfolio_value(self, exchange: str, value_usd: float):
        """Set portfolio value."""
        self.portfolio_value.labels(exchange=exchange).set(value_usd)
    
    def set_position_size(self, exchange: str, trading_pair: str, side: str, size: float):
        """Set position size."""
        self.position_size.labels(exchange=exchange, trading_pair=trading_pair, side=side).set(size)
    
    # Performance metrics
    def record_realized_pnl(self, exchange: str, trading_pair: str, pnl_usd: float):
        """Record realized PnL."""
        self.pnl_realized.labels(exchange=exchange, trading_pair=trading_pair).inc(pnl_usd)
    
    def set_unrealized_pnl(self, exchange: str, trading_pair: str, pnl_usd: float):
        """Set unrealized PnL."""
        self.pnl_unrealized.labels(exchange=exchange, trading_pair=trading_pair).set(pnl_usd)
    
    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics in text format."""
        return generate_latest(self.registry)
    
    def get_content_type(self) -> str:
        """Get content type for metrics response."""
        return CONTENT_TYPE_LATEST


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """Reset the global metrics collector (for testing)."""
    global _metrics_collector
    _metrics_collector = None


# Decorator for timing REST requests
def time_rest_request(exchange: str, endpoint: str, method: str):
    """Decorator to time REST API requests."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                get_metrics_collector().record_rest_request(exchange, endpoint, method, duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                get_metrics_collector().record_rest_request(exchange, endpoint, method, duration)
                raise
        return wrapper
    return decorator