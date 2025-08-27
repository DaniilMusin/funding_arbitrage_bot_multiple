"""
Example configuration for observability features.

This file demonstrates how to configure structured logging, Prometheus metrics,
and alerting for the Hummingbot trading system.

To use this configuration:
1. Copy this file to conf/observability_config.py
2. Modify the settings according to your needs
3. Set environment variables for sensitive data (tokens, webhooks, etc.)
"""

# Observability configuration
observability_config = {
    # Rate limiting for alerts
    "max_alerts_per_minute": 5,
    "max_alerts_per_hour": 20, 
    "max_alerts_per_day": 100,
    "dedup_window_seconds": 3600,  # 1 hour
    
    # Metrics collection
    "metrics_enabled": True,
    "metrics_port": 8080,  # Port for /metrics endpoint
    
    # Logging configuration
    "log_level": "INFO",  # Can be overridden by LOG_LEVEL env var
    "json_logging": True,  # Can be overridden by JSON_LOGGING env var
    
    # Health endpoint configuration
    "health_endpoint": {
        "enabled": True,
        "port": 8080,
        "host": "127.0.0.1"
    }
}

# Environment variables for sensitive configuration
# These should be set in your environment, not in this file
"""
# Sentry configuration
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id
ENVIRONMENT=production

# Slack configuration  
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK

# Telegram configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Logging configuration
LOG_LEVEL=INFO
JSON_LOGGING=true
"""

# Alert severity configuration
# Determines which channels receive alerts for each severity level
alert_channels_by_severity = {
    "critical": ["sentry", "slack", "telegram"],
    "high": ["sentry", "slack"],
    "medium": ["sentry"],
    "low": ["sentry"],
    "info": []  # Info alerts are only logged
}

# Component-specific alert configuration
component_alert_config = {
    "exchange": {
        "auth_errors": "high",
        "rate_limit_errors": "high", 
        "network_errors": "medium",
        "api_errors": "medium"
    },
    "trading": {
        "order_failures": "high",
        "position_limits": "critical",
        "hedge_failures": "high",
        "funding_issues": "medium"
    },
    "portfolio": {
        "balance_alerts": "medium",
        "pnl_alerts": "low"
    },
    "system": {
        "readiness_alerts": "medium",
        "performance_alerts": "low"
    }
}

# Metrics configuration
metrics_config = {
    # REST API latency buckets (in seconds)
    "rest_latency_buckets": [0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
    
    # WebSocket latency buckets (in seconds)
    "ws_latency_buckets": [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
    
    # Hedge slippage buckets (in basis points)
    "hedge_slippage_buckets": [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0],
    
    # Order fill latency buckets (in seconds)
    "order_fill_latency_buckets": [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0],
    
    # Exchanges to monitor
    "monitored_exchanges": [
        "binance",
        "okx", 
        "bybit",
        "hyperliquid",
        "vertex"
    ],
    
    # Trading pairs to monitor
    "monitored_pairs": [
        "BTC-USDT",
        "ETH-USDT", 
        "SOL-USDT"
    ]
}

# Example usage in your application:
"""
from hummingbot.core.observability.integration import setup_observability

# Initialize observability
observability = setup_observability(observability_config)

# Use structured logging
logger = observability.get_logger(__name__)

# Record metrics
observability.record_exchange_operation(
    exchange="binance",
    operation="rest_account_balance", 
    duration=0.125,
    success=True
)

# Send custom alert
await observability.send_custom_alert(
    title="Custom Alert",
    message="Something noteworthy happened",
    severity=AlertSeverity.MEDIUM,
    component="my_component"
)
"""