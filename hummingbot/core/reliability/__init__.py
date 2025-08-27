"""
Reliability and limits module for trading system.

This module provides comprehensive reliability features:

1. Enhanced Rate Limiting with Token Buckets:
   - Per-exchange rate limiting with token bucket algorithm
   - Exponential backoff with jitter for critical REST calls
   - Configurable capacity and refill rates per exchange

2. NTP Time Synchronization Monitoring:
   - Clock drift detection against NTP servers
   - Configurable drift thresholds
   - Trading halt on excessive time drift

3. Circuit Breakers:
   - Global kill switch for critical failures
   - Error series monitoring
   - Hedge deviation protection
   - Order cancellation failure detection

4. Trading Readiness Health Checks:
   - Connection status monitoring (REST, WebSocket, user streams)
   - Margin level monitoring
   - System resource checks
   - Custom health check support

5. Health Endpoints:
   - /health/live - liveness probe
   - /health/ready - readiness probe
   - /health/status - basic status
   - /health/detailed - comprehensive status

Usage Example:
--------------

```python
from hummingbot.core.reliability import ReliabilityManager, ReliabilityConfig
from hummingbot.core.utils.circuit_breakers import CircuitBreakerType
from hummingbot.core.utils.trading_readiness import ConnectionStatus

# Configure reliability settings
config = ReliabilityConfig()
config.time_sync_drift_threshold_ms = 500.0  # 500ms threshold
config.error_series_threshold = 3  # Trip after 3 errors
config.health_endpoint_port = 8080

# Initialize reliability manager
reliability_manager = ReliabilityManager(config)

async def setup_trading_system():
    # Start reliability monitoring
    await reliability_manager.start()
    
    # Configure exchange rate limits
    reliability_manager.configure_exchange_rate_limit(
        "binance", capacity=1200, refill_rate=20.0
    )
    
    # Register trading callbacks
    reliability_manager.add_trading_halted_callback(on_trading_halted)
    reliability_manager.add_trading_resumed_callback(on_trading_resumed)

async def execute_trade_with_reliability():
    # Check if trading is allowed
    if not reliability_manager.is_trading_ready():
        print("Trading not ready - aborting")
        return
    
    # Acquire rate limit tokens
    if not await reliability_manager.acquire_rate_limit("binance", tokens=1, is_critical=True):
        print("Rate limited - aborting")
        return
    
    try:
        # Execute trade
        result = await execute_trade()
        
        # Record success for circuit breaker
        reliability_manager.record_success(CircuitBreakerType.ERROR_SERIES)
        
    except Exception as e:
        # Record failure for circuit breaker
        reliability_manager.record_failure(
            CircuitBreakerType.ERROR_SERIES, 
            {"error": str(e)}
        )
        raise

async def update_system_status():
    # Update connection status
    reliability_manager.update_connection_status(
        "binance", "websocket", ConnectionStatus.CONNECTED, latency_ms=50.0
    )
    
    # Update margin status
    reliability_manager.update_margin_status(
        "binance", available_balance=10000.0, used_margin=2000.0
    )

async def on_trading_halted(reason):
    print(f"Trading halted: {reason}")
    # Implement trading halt logic

async def on_trading_resumed(reason):
    print(f"Trading resumed: {reason}")
    # Implement trading resume logic

# Health check endpoint will be available at:
# http://localhost:8080/health/ready
```

Integration with Exchange Connectors:
------------------------------------

Exchange connectors should integrate with the reliability system:

```python
class ExchangeConnector:
    def __init__(self, reliability_manager):
        self.reliability_manager = reliability_manager
    
    async def _make_api_request(self, method, endpoint, is_critical=False):
        # Check circuit breakers
        if not self.reliability_manager.can_execute_operation(CircuitBreakerType.ERROR_SERIES):
            raise Exception("Circuit breaker tripped")
        
        # Acquire rate limit
        if not await self.reliability_manager.acquire_rate_limit(
            self.exchange_name, tokens=1, is_critical=is_critical
        ):
            raise Exception("Rate limited")
        
        try:
            response = await self._execute_request(method, endpoint)
            self.reliability_manager.record_success(CircuitBreakerType.ERROR_SERIES)
            return response
        except Exception as e:
            self.reliability_manager.record_failure(
                CircuitBreakerType.ERROR_SERIES,
                {"endpoint": endpoint, "error": str(e)}
            )
            raise
    
    def _on_websocket_connected(self):
        self.reliability_manager.update_connection_status(
            self.exchange_name, "websocket", ConnectionStatus.CONNECTED
        )
    
    def _on_websocket_error(self, error):
        self.reliability_manager.update_connection_status(
            self.exchange_name, "websocket", ConnectionStatus.ERROR, error=str(error)
        )
```
"""

from .reliability_manager import ReliabilityManager, ReliabilityConfig

__all__ = [
    "ReliabilityManager",
    "ReliabilityConfig"
]