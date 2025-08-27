# Reliability and Limits System

Comprehensive reliability and limits system for the Hummingbot trading platform. This system implements advanced reliability patterns to ensure robust, fault-tolerant trading operations.

## Features

### 🚦 Enhanced Rate Limiting
- **Token Bucket Algorithm**: Per-exchange rate limiting with configurable capacity and refill rates
- **Exponential Backoff**: Critical REST calls use exponential backoff with jitter to prevent thundering herd
- **Exchange-Specific Limits**: Customizable rate limits for each exchange based on their API specifications
- **Priority Handling**: Critical operations get priority and separate backoff handling

### ⏱️ NTP Time Synchronization Monitoring
- **Clock Drift Detection**: Monitors system clock drift against multiple NTP servers
- **Configurable Thresholds**: Set maximum allowable drift (default: 1000ms)
- **Trading Halt**: Automatically halts trading when drift exceeds threshold
- **Multiple NTP Sources**: Uses pool.ntp.org, time.google.com, time.cloudflare.com, time.apple.com

### 🔐 Circuit Breakers
- **Global Kill Switch**: Emergency stop for entire trading system
- **Error Series Protection**: Trips after consecutive API errors
- **Hedge Deviation Monitoring**: Detects when hedging strategies deviate from expected behavior
- **Order Cancellation Failures**: Monitors cancellation success rates
- **Exponential Backoff**: Half-open state testing with gradual recovery

### 🏥 Trading Readiness Health Checks
- **Connection Monitoring**: REST, WebSocket, and user stream connection health
- **Margin Level Monitoring**: Available balance and margin utilization tracking
- **System Resource Checks**: CPU, memory, and disk usage monitoring
- **Custom Health Checks**: Extensible framework for additional checks

### 🌐 Health Endpoints
- **Liveness Probe**: `/health/live` - Service is responding
- **Readiness Probe**: `/health/ready` - Service is ready to handle traffic
- **Status Summary**: `/health/status` - Basic system status
- **Detailed Status**: `/health/detailed` - Comprehensive system information

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Reliability Manager                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │ Rate Limiter    │  │ Time Sync       │  │ Circuit      │ │
│  │ • Token Bucket  │  │ • NTP Monitor   │  │ Breakers     │ │
│  │ • Backoff       │  │ • Drift Check   │  │ • Kill Switch│ │
│  │ • Per-Exchange  │  │ • Auto Halt     │  │ • Error Track│ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────────────────────────┐ │
│  │ Trading Ready   │  │ Health Endpoints                    │ │
│  │ • Connections   │  │ • /health/live                      │ │
│  │ • Margins       │  │ • /health/ready                     │ │
│  │ • Resources     │  │ • /health/status                    │ │
│  └─────────────────┘  │ • /health/detailed                  │ │
│                       └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Basic Usage

```python
from hummingbot.core.reliability import ReliabilityManager, ReliabilityConfig

# Create configuration
config = ReliabilityConfig()
config.time_sync_drift_threshold_ms = 500.0
config.error_series_threshold = 3
config.health_endpoint_port = 8080

# Initialize reliability manager
reliability_manager = ReliabilityManager(config)

# Start monitoring
await reliability_manager.start()

# Configure exchange limits
reliability_manager.configure_exchange_rate_limit(
    "binance", capacity=1200, refill_rate=20.0
)

# Check if trading is ready
if reliability_manager.is_trading_ready():
    print("System ready for trading")

# Acquire rate limit tokens
if await reliability_manager.acquire_rate_limit("binance", tokens=1, is_critical=True):
    # Execute trade
    pass
```

### Integration with Exchange Connectors

```python
class ExchangeConnector:
    def __init__(self, reliability_manager):
        self.reliability_manager = reliability_manager
    
    async def make_api_request(self, endpoint, is_critical=False):
        # Check circuit breakers
        if not self.reliability_manager.can_execute_operation(CircuitBreakerType.ERROR_SERIES):
            raise Exception("Circuit breaker tripped")
        
        # Acquire rate limit
        if not await self.reliability_manager.acquire_rate_limit(
            self.exchange_name, tokens=1, is_critical=is_critical
        ):
            raise Exception("Rate limited")
        
        try:
            response = await self._execute_request(endpoint)
            self.reliability_manager.record_success(CircuitBreakerType.ERROR_SERIES)
            return response
        except Exception as e:
            self.reliability_manager.record_failure(CircuitBreakerType.ERROR_SERIES)
            raise
```

## Configuration

### Environment-Specific Configurations

#### Production
```python
config = ReliabilityConfig()
config.time_sync_drift_threshold_ms = 250.0    # Strict timing
config.error_series_threshold = 3              # Conservative
config.readiness_check_interval = 15.0         # Frequent checks
```

#### Development
```python
config = ReliabilityConfig()
config.time_sync_drift_threshold_ms = 1000.0   # Relaxed timing
config.error_series_threshold = 10             # More forgiving
config.readiness_check_interval = 60.0         # Less frequent
```

#### High-Frequency Trading
```python
config = ReliabilityConfig()
config.time_sync_drift_threshold_ms = 50.0     # Very strict timing
config.error_series_threshold = 2              # Immediate response
config.readiness_check_interval = 5.0          # Continuous monitoring
```

### Exchange Rate Limits

Pre-configured rate limits for major exchanges:

```python
EXCHANGE_LIMITS = {
    "binance": {"capacity": 1200, "refill_rate": 20.0},
    "coinbase": {"capacity": 100, "refill_rate": 10.0},
    "kraken": {"capacity": 60, "refill_rate": 1.0},
    "okx": {"capacity": 300, "refill_rate": 5.0},
    "bybit": {"capacity": 600, "refill_rate": 10.0}
}
```

## Health Monitoring

### Health Endpoints

The system provides HTTP endpoints for monitoring:

- **Liveness**: `GET /health/live`
  ```json
  {
    "status": "alive",
    "timestamp": 1642681234.567,
    "uptime_seconds": 3600,
    "version": "1.0.0"
  }
  ```

- **Readiness**: `GET /health/ready`
  ```json
  {
    "status": "ready",
    "timestamp": 1642681234.567,
    "message": "All systems ready"
  }
  ```

- **Detailed Status**: `GET /health/detailed`
  ```json
  {
    "timestamp": 1642681234.567,
    "overall_ready": true,
    "time_sync": {
      "is_trading_allowed": true,
      "current_drift_ms": 45.2
    },
    "circuit_breakers": {
      "can_trade": true,
      "global_kill_switch_active": false
    },
    "trading_readiness": {
      "healthy": true,
      "connections": {...},
      "margins": {...}
    }
  }
  ```

### Monitoring Integration

Integrate with monitoring systems:

```bash
# Kubernetes liveness probe
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

# Kubernetes readiness probe
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Demo and Testing

### Run the Demo

```bash
python scripts/reliability_demo.py
```

The demo simulates:
- Multiple exchange connections
- Trading operations with failures
- Margin level changes
- Circuit breaker trips
- Rate limiting scenarios

### Monitor During Demo

- Health endpoint: http://localhost:8080/health/ready
- Detailed status: http://localhost:8080/health/detailed
- Console logs show real-time system behavior

### Testing Components

Each component can be tested independently:

```python
# Test rate limiter
rate_limiter = EnhancedRateLimiter()
assert await rate_limiter.acquire_tokens("binance", 1)

# Test time sync
time_monitor = TimeSyncMonitor(drift_threshold_ms=100.0)
drift = await time_monitor.measure_drift()

# Test circuit breakers
cb_manager = CircuitBreakerManager()
cb_manager.record_failure(CircuitBreakerType.ERROR_SERIES)
```

## Deployment Considerations

### Production Deployment

1. **Resource Requirements**:
   - CPU: Low (< 5% additional overhead)
   - Memory: ~50MB for monitoring components
   - Network: Periodic NTP requests

2. **Configuration**:
   - Use strict time sync thresholds (< 500ms)
   - Conservative circuit breaker settings
   - Enable all monitoring components

3. **Monitoring**:
   - Set up alerts on health endpoints
   - Monitor circuit breaker trips
   - Track rate limiting utilization

### Security Considerations

- Health endpoints on internal networks only
- Monitor for excessive rate limiting (possible DoS)
- Secure NTP server configuration
- Circuit breaker override controls

### Performance Impact

- Rate limiting: ~1-2ms per request overhead
- Time sync: NTP check every 30-60 seconds
- Health checks: Minimal CPU usage
- Circuit breakers: Negligible overhead

## Troubleshooting

### Common Issues

1. **Time Drift Failures**:
   - Check NTP server connectivity
   - Verify system clock configuration
   - Consider increasing drift threshold temporarily

2. **Circuit Breaker Trips**:
   - Check exchange API status
   - Review error logs for patterns
   - Consider adjusting thresholds for specific environments

3. **Rate Limiting Issues**:
   - Verify exchange API limits
   - Adjust token bucket capacity/refill rate
   - Check for request spikes

4. **Health Check Failures**:
   - Verify exchange connections
   - Check margin levels
   - Review system resources

### Debugging

Enable debug logging:

```python
import logging
logging.getLogger("hummingbot.core.reliability").setLevel(logging.DEBUG)
```

Check component status:

```python
status = reliability_manager.get_comprehensive_status()
print(json.dumps(status, indent=2))
```

## Contributing

The reliability system is designed to be extensible:

1. **Custom Health Checks**: Implement additional health checks
2. **New Circuit Breakers**: Add domain-specific circuit breakers
3. **Enhanced Metrics**: Add more detailed monitoring
4. **Configuration Options**: Extend configuration capabilities

See the existing implementations as examples for adding new components.

## License

This reliability system is part of the Hummingbot project and follows the same licensing terms.