#!/usr/bin/env python3
"""
Observability demo script showing structured logging, metrics, and alerting.

This script demonstrates the key features of the observability system:
- Structured JSON logging with correlation IDs
- Prometheus metrics collection
- Alerting with rate limiting and deduplication

Run with: python scripts/observability_demo.py
"""

import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from hummingbot.core.observability import (
    setup_observability,
    AlertSeverity,
    log_exchange_operation,
    log_trading_operation
)
from hummingbot.logger.observability_logger import get_observability_logger


async def demo_structured_logging():
    """Demonstrate structured logging features."""
    print("=== Structured Logging Demo ===")
    
    # Get observability logger
    logger = get_observability_logger("demo")
    
    # Basic structured logging
    logger.info_structured(
        "Demo started",
        demo_type="observability",
        features=["logging", "metrics", "alerting"]
    )
    
    # Logging with correlation ID
    with logger.with_correlation_id("demo-correlation-123"):
        logger.info_structured(
            "Processing exchange operation",
            exchange="binance",
            operation="get_account_balance"
        )
        
        # Nested operations keep the same correlation ID
        logger.debug_structured(
            "Making REST API call",
            endpoint="/api/v3/account",
            method="GET"
        )
        
        logger.info_structured(
            "Operation completed successfully",
            duration_ms=125,
            status="success"
        )
    
    # Logging with exchange context
    with logger.with_exchange_context("okx", "BTC-USDT"):
        logger.info_structured(
            "Processing trading operation",
            operation="place_order",
            side="buy",
            amount=0.001
        )
        
        logger.warning_structured(
            "Order partially filled",
            filled_amount=0.0008,
            remaining=0.0002
        )


async def demo_metrics():
    """Demonstrate metrics collection."""
    print("\n=== Metrics Demo ===")
    
    observability = setup_observability()
    
    # Simulate exchange operations
    print("Recording exchange operations...")
    
    # REST API calls
    observability.record_exchange_operation(
        exchange="binance",
        operation="rest_account_balance",
        duration=0.125,
        success=True
    )
    
    observability.record_exchange_operation(
        exchange="okx", 
        operation="rest_place_order",
        duration=0.234,
        success=True
    )
    
    # WebSocket reconnections
    observability.metrics.record_ws_reconnect("binance", "user_stream")
    observability.metrics.record_ws_latency("binance", "order_book", 0.025)
    
    # Trading operations
    print("Recording trading operations...")
    
    observability.record_trading_operation(
        exchange="binance",
        trading_pair="BTC-USDT",
        operation="order_created",
        side="buy",
        order_type="limit"
    )
    
    observability.record_trading_operation(
        exchange="binance", 
        trading_pair="BTC-USDT",
        operation="order_filled",
        side="buy",
        fill_latency=2.5
    )
    
    observability.record_trading_operation(
        exchange="binance",
        trading_pair="BTC-USDT", 
        operation="commission_paid",
        side="buy",
        amount=0.025
    )
    
    # Portfolio updates
    print("Updating portfolio metrics...")
    
    observability.update_portfolio_metrics("binance", {
        "total_value_usd": 10000.0,
        "positions": [
            {
                "trading_pair": "BTC-USDT",
                "side": "long",
                "size": 0.25
            }
        ],
        "unrealized_pnl": {
            "BTC-USDT": 150.0
        }
    })
    
    # Funding metrics
    observability.update_funding_metrics(
        exchange="binance",
        trading_pair="BTC-USDT", 
        expected_funding=12.50,
        captured_funding=12.45
    )
    
    # Trading readiness
    observability.set_trading_readiness("exchange_connection", True)
    observability.set_trading_readiness("balance_check", True)
    observability.set_trading_readiness("position_limits", False)  # This will trigger an alert
    
    print("Metrics recorded successfully!")


async def demo_alerting():
    """Demonstrate alerting system.""" 
    print("\n=== Alerting Demo ===")
    
    observability = setup_observability()
    
    # Send alerts of different severities
    print("Sending test alerts...")
    
    # Info alert (only logged)
    await observability.send_custom_alert(
        title="System Information",
        message="Demo script is running observability tests",
        severity=AlertSeverity.INFO,
        component="demo"
    )
    
    # Medium severity alert
    await observability.send_custom_alert(
        title="Trading Alert",
        message="Position limit check failed", 
        severity=AlertSeverity.MEDIUM,
        component="trading_readiness",
        metadata={"component": "position_limits"}
    )
    
    # High severity alert
    await observability.send_custom_alert(
        title="Exchange Error",
        message="Authentication failed for Binance API",
        severity=AlertSeverity.HIGH,
        component="exchange",
        exchange="binance",
        error_type="auth_error"
    )
    
    # Critical alert
    await observability.send_custom_alert(
        title="System Critical",
        message="Multiple exchange connections lost",
        severity=AlertSeverity.CRITICAL,
        component="system",
        metadata={
            "affected_exchanges": ["binance", "okx", "bybit"],
            "timestamp": time.time()
        }
    )
    
    # Test rate limiting - send multiple similar alerts
    print("Testing rate limiting...")
    for i in range(10):
        await observability.send_custom_alert(
            title="Rate Limit Test",
            message=f"Test alert #{i+1}",
            severity=AlertSeverity.LOW,
            component="demo",
            metadata={"test_id": i}
        )
    
    print("Alerts sent! Check your configured channels for delivery.")


async def demo_metrics_endpoint():
    """Demonstrate the metrics endpoint."""
    print("\n=== Metrics Endpoint Demo ===")
    
    try:
        from hummingbot.core.api.health_endpoint import HealthEndpoint
        
        # Start health endpoint with metrics
        health_endpoint = HealthEndpoint(port=8080, host="127.0.0.1")
        
        print("Starting health endpoint on http://127.0.0.1:8080")
        print("Available endpoints:")
        print("  - http://127.0.0.1:8080/health/live")
        print("  - http://127.0.0.1:8080/health/ready") 
        print("  - http://127.0.0.1:8080/health/status")
        print("  - http://127.0.0.1:8080/metrics")
        
        await health_endpoint.start()
        
        # Keep running for a bit to allow testing
        print("\nHealth endpoint is running. You can test the endpoints with curl:")
        print("  curl http://127.0.0.1:8080/health/live")
        print("  curl http://127.0.0.1:8080/metrics")
        print("\nPress Ctrl+C to stop...")
        
        try:
            await asyncio.sleep(30)  # Run for 30 seconds
        except KeyboardInterrupt:
            print("\nStopping health endpoint...")
        
        await health_endpoint.stop()
        
    except Exception as e:
        print(f"Could not start health endpoint: {e}")
        print("This is expected if the port is already in use.")


def print_environment_setup():
    """Print information about environment setup."""
    print("\n=== Environment Setup ===")
    print("To enable full observability features, set these environment variables:")
    print()
    print("# Logging configuration")
    print("export LOG_LEVEL=INFO")
    print("export JSON_LOGGING=true")
    print()
    print("# Sentry alerting")
    print("export SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id")
    print("export ENVIRONMENT=production")
    print()
    print("# Slack alerting")
    print("export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK")
    print()
    print("# Telegram alerting")
    print("export TELEGRAM_BOT_TOKEN=your_bot_token_here")
    print("export TELEGRAM_CHAT_ID=your_chat_id_here")
    print()
    print("Current environment:")
    env_vars = [
        'LOG_LEVEL', 'JSON_LOGGING', 'SENTRY_DSN', 'ENVIRONMENT',
        'SLACK_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'
    ]
    for var in env_vars:
        value = os.getenv(var, 'Not set')
        # Hide sensitive values
        if value != 'Not set' and var in ['SENTRY_DSN', 'SLACK_WEBHOOK_URL', 'TELEGRAM_BOT_TOKEN']:
            value = value[:20] + "..." if len(value) > 20 else value
        print(f"  {var}: {value}")


async def main():
    """Run the observability demo."""
    print("Hummingbot Observability System Demo")
    print("====================================")
    
    print_environment_setup()
    
    # Run demos
    await demo_structured_logging()
    await demo_metrics()
    await demo_alerting()
    await demo_metrics_endpoint()
    
    print("\n=== Demo Complete ===")
    print("The observability system is now ready for use!")
    print("Check the configuration example in conf/observability_config_example.py")


if __name__ == "__main__":
    asyncio.run(main())