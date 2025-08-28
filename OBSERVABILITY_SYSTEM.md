# Hummingbot Observability System

Comprehensive observability implementation for the Hummingbot trading system with structured logging, Prometheus metrics, and multi-channel alerting.

## Features

### 📊 Structured Logging
- **JSON format** with correlation IDs per exchange operation
- **Context preservation** across async operations  
- **Log level configuration** via environment variables
- **Exchange and trading pair context** tracking

### 📈 Prometheus Metrics
- **REST API latency** (request duration, success/failure rates)
- **WebSocket metrics** (reconnection frequency, message processing delay)
- **Trading metrics** (order fills, cancellations, latency)
- **Funding capture** (expected vs actual)
- **Funding P&L decomposition** (expected vs realized, USD)
- **Commission tracking** by exchange and trading pair
- **Hedge slippage** monitoring
- **Error rates** by type and component
- **Error streak length** by type/component (bucket-friendly for alerting)
- **Trading readiness SLA** monitoring
- **Portfolio metrics** (value, positions, PnL)
- **Rate-limit tokens remaining** per bucket
- **Time to settlement** per exchange/pair

### 🚨 Alerting System
- **Multi-channel delivery**: Sentry, Slack, Telegram
- **Rate limiting** to prevent spam (configurable per minute/hour/day)
- **Deduplication** with configurable time windows
- **Severity-based routing** (critical → all channels, info → logs only)
- **Correlation ID tracking** for alert context

## Quick Start

### 1. Install Dependencies

The observability system requires these packages (automatically installed with setup.py):
```bash
pip install prometheus-client>=0.19.0 sentry-sdk>=1.40.0
```

### 2. Environment Configuration

Set up environment variables for full functionality:

```bash
# Logging
export LOG_LEVEL=INFO
export JSON_LOGGING=true

# Sentry (optional)
export SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
export ENVIRONMENT=production

# Slack (optional)  
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK

# Telegram (optional)
export TELEGRAM_BOT_TOKEN=your_bot_token_here
export TELEGRAM_CHAT_ID=your_chat_id_here
```

### 3. Basic Usage

```python
from hummingbot.core.observability import setup_observability

# Initialize observability
observability = setup_observability()

# Get structured logger
logger = observability.get_logger(__name__)

# Log with correlation ID and context
with logger.with_correlation_id("trade-001"):
    with logger.with_exchange_context("binance", "BTC-USDT"):
        logger.info_structured(
            "Order placed successfully",
            order_id="123456",
            side="buy",
            amount=0.001
        )

# Record metrics
observability.record_trading_operation(
    exchange="binance",
    trading_pair="BTC-USDT", 
    operation="order_filled",
    side="buy",
    fill_latency=2.5
)

# Send alerts
from hummingbot.core.observability import AlertSeverity
await observability.send_custom_alert(
    title="Trading Alert",
    message="High slippage detected",
    severity=AlertSeverity.HIGH,
    component="trading",
    exchange="binance"
)
```

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                 Observability System                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────┐ │
│  │ Structured      │  │ Prometheus      │  │ Alerting │ │
│  │ Logging         │  │ Metrics         │  │ System   │ │
│  │                 │  │                 │  │          │ │
│  │ • JSON format   │  │ • REST latency  │  │ • Sentry │ │
│  │ • Correlation   │  │ • WS reconnects │  │ • Slack  │ │
│  │ • Context       │  │ • Order metrics │  │ • Telegram│ │
│  │ • Log levels    │  │ • Funding data  │  │ • Rate   │ │
│  │                 │  │ • Commission    │  │   limiting│ │
│  └─────────────────┘  └─────────────────┘  └──────────┘ │
├─────────────────────────────────────────────────────────┤
│                Integration Layer                        │
├─────────────────────────────────────────────────────────┤
│           Health Endpoint (/metrics, /health)          │
└─────────────────────────────────────────────────────────┘
```

### Key Components

#### 1. ObservabilityLogger
Enhanced logger with structured JSON output and correlation ID tracking:

```python
from hummingbot.logger.observability_logger import get_observability_logger

logger = get_observability_logger(__name__)

# Structured logging with automatic correlation ID
with logger.with_correlation_id():
    logger.info_structured("Operation started", operation="place_order")
    
# Exchange context preservation
with logger.with_exchange_context("binance", "BTC-USDT"):
    logger.error_structured("API error", error_code=1001)
```

#### 2. MetricsCollector
Prometheus metrics collection with trading-specific metrics:

```python
from hummingbot.core.observability.metrics import get_metrics_collector

metrics = get_metrics_collector()

# Record REST API timing
metrics.record_rest_request("binance", "account", "GET", 0.125)

# Track order lifecycle
metrics.record_order_created("binance", "BTC-USDT", "buy", "limit")
metrics.record_order_filled("binance", "BTC-USDT", "buy", fill_latency=2.5)

# Monitor funding
metrics.set_funding_expected("binance", "BTC-USDT", 12.50)
metrics.set_funding_captured("binance", "BTC-USDT", "actual", 12.45)
```

#### 3. AlertManager
Multi-channel alerting with rate limiting and deduplication:

```python
from hummingbot.core.observability.alerting import get_alert_manager, AlertSeverity

alert_manager = get_alert_manager()

# Create and send alert
alert = alert_manager.create_alert(
    title="Exchange Error",
    message="API authentication failed",
    severity=AlertSeverity.HIGH,
    component="exchange",
    exchange="binance"
)

await alert_manager.send_alert(alert)
```

## Metrics Reference

### REST API Metrics
- `hummingbot_rest_request_duration_seconds` - Request latency histogram
- Labels: `exchange`, `endpoint`, `method`

### WebSocket Metrics  
- `hummingbot_websocket_reconnects_total` - Reconnection counter
- `hummingbot_websocket_message_delay_seconds` - Message processing delay
- Labels: `exchange`, `stream_type`

### Trading Metrics
- `hummingbot_orders_created_total` - Orders created counter
- `hummingbot_orders_filled_total` - Orders filled counter  
- `hummingbot_orders_cancelled_total` - Orders cancelled counter
- `hummingbot_order_fill_latency_seconds` - Fill time histogram
- Labels: `exchange`, `trading_pair`, `side`, `order_type`

### Financial Metrics
- `hummingbot_funding_captured_total` - Funding captured gauge
- `hummingbot_funding_expected_total` - Expected funding gauge
- `hummingbot_funding_pnl_expected_usd` - Expected funding P&L (USD)
- `hummingbot_funding_pnl_realized_usd_total` - Realized funding P&L (USD)
- `hummingbot_commissions_paid_total` - Commission counter
- `hummingbot_hedge_slippage_bps` - Slippage histogram
- `hummingbot_portfolio_value_usd` - Portfolio value gauge
- `hummingbot_pnl_realized_usd_total` - Realized PnL counter
- `hummingbot_pnl_unrealized_usd` - Unrealized PnL gauge

### System Metrics
- `hummingbot_errors_total` - Error counter by type
- `hummingbot_error_streak_length` - Current consecutive error streak
- `hummingbot_trading_readiness` - Readiness status gauge
- `hummingbot_readiness_uptime_seconds_total` - Uptime counter
- Labels vary by metric type

### Rate Limits & Settlement
- `hummingbot_rate_limit_tokens_remaining{exchange, bucket}` - Remaining tokens in bucket
- `hummingbot_time_to_settlement_seconds{exchange, trading_pair}` - Time until settlement

### Edge Metrics and Entry Logic

- `hummingbot_edge_value{exchange,trading_pair}` - Computed edge value
- `hummingbot_edge_component{exchange,trading_pair,component}` - Components: `expected_funding`, `fees_perp`, `fees_spot`, `borrow_cost`, `slippage_buffer`

Formula and gate:

```
edge = expected_funding - (fees_perp + fees_spot + borrow_cost) - slippage_buffer
enter = edge >= min_edge && readiness_ok && risk_budgets_ok
```

## Alerting Configuration

### Severity Levels
- **CRITICAL**: System failures, multiple exchange outages → All channels
- **HIGH**: Auth errors, rate limits, order failures → Sentry + Slack  
- **MEDIUM**: Network issues, readiness problems → Sentry only
- **LOW**: Performance warnings → Sentry only
- **INFO**: Informational messages → Logs only

### Rate Limiting
Default limits (configurable):
- 5 alerts per minute
- 20 alerts per hour  
- 100 alerts per day
- 1 hour deduplication window

### Channel Configuration

#### Sentry
```bash
export SENTRY_DSN=https://your-dsn@sentry.io/project-id
export ENVIRONMENT=production
```

#### Slack
```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK
```

#### Telegram
```bash
export TELEGRAM_BOT_TOKEN=your_bot_token
export TELEGRAM_CHAT_ID=your_chat_id
```

## Endpoints

### Health Endpoints
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe  
- `GET /health/status` - Basic status
- `GET /health/detailed` - Detailed system status

### Metrics Endpoint
- `GET /metrics` - Prometheus metrics (text format)

Example Prometheus scrape configuration:
```yaml
scrape_configs:
  - job_name: 'hummingbot'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

## Advanced Usage

### Custom Metrics
```python
from hummingbot.core.observability.metrics import get_metrics_collector
from prometheus_client import Counter

# Add custom metric to the registry
metrics = get_metrics_collector()
custom_counter = Counter(
    'my_custom_metric_total', 
    'Custom metric description',
    ['label1', 'label2'],
    registry=metrics.registry
)

custom_counter.labels(label1='value1', label2='value2').inc()
```

### Integration with Trading Strategies
```python
from hummingbot.core.observability import log_exchange_operation

class MyStrategy:
    def __init__(self):
        self.observability = setup_observability()
    
    async def place_order(self, exchange, trading_pair, side, amount):
        correlation_id = new_correlation_id()
        
        with self.observability.get_logger(__name__).with_correlation_id(correlation_id):
            try:
                # Record order creation
                self.observability.record_trading_operation(
                    exchange=exchange,
                    trading_pair=trading_pair,
                    operation="order_created",
                    side=side,
                    order_type="limit"
                )
                
                # Place order logic here...
                order = await self._place_order_internal(exchange, trading_pair, side, amount)
                
                # Record success
                self.observability.get_logger(__name__).info_structured(
                    "Order placed successfully",
                    order_id=order.id,
                    exchange=exchange,
                    trading_pair=trading_pair
                )
                
                return order
                
            except Exception as e:
                # Record error and send alert
                await self.observability.send_custom_alert(
                    title="Order Placement Failed",
                    message=f"Failed to place order: {str(e)}",
                    severity=AlertSeverity.HIGH,
                    component="trading",
                    exchange=exchange,
                    trading_pair=trading_pair
                )
                raise
```

### Monitoring Dashboard

Example Grafana queries for key metrics:

```prometheus
# REST API latency 95th percentile
histogram_quantile(0.95, 
  rate(hummingbot_rest_request_duration_seconds_bucket[5m])
)

# WebSocket reconnection rate
rate(hummingbot_websocket_reconnects_total[5m])

# Order fill rate
rate(hummingbot_orders_filled_total[5m]) / 
rate(hummingbot_orders_created_total[5m])

# Trading readiness SLA
avg_over_time(hummingbot_trading_readiness[1h])

# Funding capture efficiency  
hummingbot_funding_captured_total / hummingbot_funding_expected_total

# Funding P&L realized vs expected (5m rate)
rate(hummingbot_funding_pnl_realized_usd_total[5m])
/
avg_over_time(hummingbot_funding_pnl_expected_usd[5m])

# Rate-limit headroom
min_over_time(hummingbot_rate_limit_tokens_remaining[5m])

# Time to settlement watch
min_over_time(hummingbot_time_to_settlement_seconds[15m])

# Error streaks
max_over_time(hummingbot_error_streak_length[15m])
```

### Dashboards
Ready-to-import Grafana JSON is provided in `grafana/dashboards/hummingbot-observability.json`.

### Alerting Rules
PrometheusRule examples (more in `k8s/helm/prometheus-rules.yaml`):

```yaml
groups:
  - name: hummingbot-alerts
    rules:
      - alert: ErrorStreakHigh
        expr: max_over_time(hummingbot_error_streak_length[5m]) > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: Consecutive error streak is high
          description: Error streak > 5 for 10 minutes

      - alert: RateLimitLowHeadroom
        expr: min_over_time(hummingbot_rate_limit_tokens_remaining[5m]) < 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: Rate-limit tokens running low
          description: Remaining tokens < 10 for 5 minutes

      - alert: SettlementImminent
        expr: min_over_time(hummingbot_time_to_settlement_seconds[10m]) < 60
        for: 5m
        labels:
          severity: info
        annotations:
          summary: Settlement event in under a minute
          description: Time to settlement is below 60s

      - alert: FundingPnLDeviates
        expr: |
          rate(hummingbot_funding_pnl_realized_usd_total[15m])
          < 0.8 * avg_over_time(hummingbot_funding_pnl_expected_usd[15m])
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: Realized funding P&L below expected
          description: Realized funding P&L is lagging behind expected
```

## Testing

Run the observability demo to test all features:

```bash
python scripts/observability_demo.py
```

This script demonstrates:
- Structured logging with correlation IDs
- Metrics collection and recording
- Alert generation and rate limiting
- Health endpoint functionality

## Troubleshooting

### Common Issues

#### 1. Alerts Not Sending
- Check environment variables are set correctly
- Verify webhook URLs and tokens
- Check rate limiting hasn't suppressed alerts
- Review logs for error messages

#### 2. Metrics Not Appearing
- Ensure `/metrics` endpoint is accessible
- Check Prometheus scrape configuration
- Verify metrics are being recorded with correct labels

#### 3. JSON Logging Not Working
- Set `JSON_LOGGING=true` environment variable
- Check logger configuration in your application
- Verify log handlers are properly configured

#### 4. High Memory Usage
- Monitor metrics registry size
- Consider metric label cardinality
- Use appropriate bucketing for histograms

### Log Analysis

Example log queries for structured logs:

```bash
# Find all logs for a specific correlation ID
grep '"correlation_id":"trade-001"' logs/

# Find all errors from a specific exchange
grep '"exchange":"binance"' logs/ | grep '"level":"ERROR"'

# Find all order operations
grep '"operation":".*order"' logs/
```

## Configuration Files

### Example Configuration
See `conf/observability_config_example.py` for a complete configuration example.

### Environment Variables
All sensitive configuration should use environment variables:
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `JSON_LOGGING` - Enable JSON formatted logs (true/false)
- `SENTRY_DSN` - Sentry project DSN
- `SLACK_WEBHOOK_URL` - Slack webhook URL
- `TELEGRAM_BOT_TOKEN` - Telegram bot token
- `TELEGRAM_CHAT_ID` - Telegram chat ID

## Performance Considerations

### Metrics Collection
- Metrics are collected in-memory with minimal overhead
- Label cardinality should be kept reasonable (< 1000 unique combinations)
- High-frequency operations use efficient data structures

### Logging Performance
- Structured logging adds ~10-20% overhead vs plain text
- JSON serialization is optimized with ujson when available
- Log level filtering reduces overhead for disabled levels

### Alerting Efficiency
- Rate limiting prevents excessive API calls
- Deduplication reduces redundant notifications
- Async delivery doesn't block trading operations

## Security

### Sensitive Data Handling
- Log sanitization prevents credential leakage
- Environment variables for all secrets
- Optional log redaction for sensitive fields

### Network Security
- HTTPS for all external alert channels
- Webhook URL validation
- Rate limiting prevents abuse

## License

This observability system is part of the Hummingbot project and follows the same Apache 2.0 license.