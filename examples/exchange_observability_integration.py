"""
Example integration of observability features into an exchange connector.

This example shows how to add structured logging, metrics, and alerting
to an existing exchange connector.
"""

import asyncio
import time
from typing import Optional

from hummingbot.core.observability import (
    setup_observability,
    AlertSeverity,
    ErrorType,
    time_rest_request
)
from hummingbot.logger.observability_logger import get_observability_logger, new_correlation_id


class ObservableExchangeConnector:
    """
    Example exchange connector with observability features.
    
    This demonstrates how to integrate:
    - Structured logging with correlation IDs
    - REST API timing metrics
    - WebSocket reconnection tracking
    - Error monitoring and alerting
    - Trading operation metrics
    """
    
    def __init__(self, exchange_name: str):
        self.exchange_name = exchange_name
        
        # Initialize observability
        self.observability = setup_observability()
        self.logger = get_observability_logger(f"exchange.{exchange_name}")
        self.metrics = self.observability.metrics
        
        # WebSocket state
        self.ws_connected = False
        self.reconnect_count = 0
        
        self.logger.info_structured(
            "Exchange connector initialized",
            exchange=exchange_name,
            features=["observability", "metrics", "alerting"]
        )
    
    @time_rest_request("binance", "account_balance", "GET")
    async def get_account_balance(self) -> dict:
        """Get account balance with automatic timing metrics."""
        correlation_id = new_correlation_id()
        
        with self.logger.with_correlation_id(correlation_id):
            with self.logger.with_exchange_context(self.exchange_name):
                self.logger.info_structured(
                    "Fetching account balance",
                    operation="get_account_balance"
                )
                
                try:
                    # Simulate API call
                    await asyncio.sleep(0.1)  # Simulated network delay
                    
                    balance_data = {
                        "BTC": {"free": 1.0, "locked": 0.0},
                        "USDT": {"free": 10000.0, "locked": 500.0}
                    }
                    
                    # Calculate total portfolio value
                    total_value = 10000.0 + (1.0 * 50000.0)  # Simulated BTC price
                    self.metrics.set_portfolio_value(self.exchange_name, total_value)
                    
                    self.logger.info_structured(
                        "Account balance fetched successfully",
                        balance_count=len(balance_data),
                        total_value_usd=total_value
                    )
                    
                    return balance_data
                    
                except Exception as e:
                    # Record error metrics
                    self.metrics.record_error(
                        self.exchange_name, 
                        ErrorType.API_ERROR, 
                        "get_account_balance"
                    )
                    
                    # Log error with context
                    self.logger.error_structured(
                        "Failed to fetch account balance",
                        error=str(e),
                        operation="get_account_balance"
                    )
                    
                    # Send alert for API errors
                    await self.observability.send_custom_alert(
                        title=f"API Error: {self.exchange_name}",
                        message=f"Failed to fetch account balance: {str(e)}",
                        severity=AlertSeverity.MEDIUM,
                        component="exchange",
                        exchange=self.exchange_name,
                        error_type="api_error"
                    )
                    
                    raise
    
    async def place_order(self, trading_pair: str, side: str, amount: float, price: float) -> dict:
        """Place order with comprehensive observability."""
        correlation_id = new_correlation_id()
        order_id = f"order_{int(time.time() * 1000)}"
        
        with self.logger.with_correlation_id(correlation_id):
            with self.logger.with_exchange_context(self.exchange_name, trading_pair):
                
                # Record order creation
                self.metrics.record_order_created(
                    self.exchange_name, trading_pair, side, "limit"
                )
                
                self.logger.info_structured(
                    "Placing order",
                    order_id=order_id,
                    side=side,
                    amount=amount,
                    price=price,
                    operation="place_order"
                )
                
                start_time = time.time()
                
                try:
                    # Simulate order placement
                    await asyncio.sleep(0.2)  # API call delay
                    
                    # Simulate occasional failures
                    if amount > 10.0:  # Simulate size limit
                        raise Exception("Order size exceeds maximum allowed")
                    
                    order_data = {
                        "order_id": order_id,
                        "status": "open",
                        "side": side,
                        "amount": amount,
                        "price": price,
                        "filled": 0.0,
                        "timestamp": time.time()
                    }
                    
                    # Record successful placement
                    placement_time = time.time() - start_time
                    
                    self.logger.info_structured(
                        "Order placed successfully",
                        order_id=order_id,
                        placement_time_ms=placement_time * 1000,
                        status="open"
                    )
                    
                    # Simulate order fill after delay
                    asyncio.create_task(self._simulate_order_fill(order_data, correlation_id))
                    
                    return order_data
                    
                except Exception as e:
                    # Record error
                    self.metrics.record_error(
                        self.exchange_name,
                        ErrorType.API_ERROR,
                        "place_order"
                    )
                    
                    self.logger.error_structured(
                        "Order placement failed",
                        order_id=order_id,
                        error=str(e),
                        side=side,
                        amount=amount
                    )
                    
                    # Send high severity alert for order failures
                    await self.observability.send_custom_alert(
                        title=f"Order Placement Failed: {self.exchange_name}",
                        message=f"Failed to place {side} order for {amount} {trading_pair}: {str(e)}",
                        severity=AlertSeverity.HIGH,
                        component="trading",
                        exchange=self.exchange_name,
                        trading_pair=trading_pair,
                        metadata={
                            "order_id": order_id,
                            "side": side,
                            "amount": amount,
                            "price": price
                        }
                    )
                    
                    raise
    
    async def _simulate_order_fill(self, order_data: dict, correlation_id: str):
        """Simulate order fill with metrics recording."""
        await asyncio.sleep(2.0)  # Simulate fill delay
        
        with self.logger.with_correlation_id(correlation_id):
            trading_pair = "BTC-USDT"  # For demo
            
            # Record order fill
            fill_latency = 2.0  # Time to fill
            self.metrics.record_order_filled(
                self.exchange_name, 
                trading_pair,
                order_data["side"],
                fill_latency
            )
            
            # Record commission
            commission = order_data["amount"] * order_data["price"] * 0.001  # 0.1% fee
            self.metrics.record_commission(
                self.exchange_name,
                trading_pair, 
                order_data["side"],
                commission
            )
            
            # Simulate hedge slippage
            expected_price = order_data["price"]
            actual_price = expected_price * (1 + 0.002)  # 0.2% slippage
            slippage_bps = abs(actual_price - expected_price) / expected_price * 10000
            
            self.metrics.record_hedge_slippage(
                self.exchange_name,
                trading_pair,
                order_data["side"],
                slippage_bps
            )
            
            self.logger.info_structured(
                "Order filled",
                order_id=order_data["order_id"],
                fill_latency_seconds=fill_latency,
                commission=commission,
                slippage_bps=slippage_bps
            )
    
    async def connect_websocket(self):
        """Connect WebSocket with reconnection tracking."""
        correlation_id = new_correlation_id()
        
        with self.logger.with_correlation_id(correlation_id):
            with self.logger.with_exchange_context(self.exchange_name):
                
                self.logger.info_structured(
                    "Connecting WebSocket",
                    stream_type="user_data",
                    attempt=self.reconnect_count + 1
                )
                
                try:
                    # Simulate connection
                    await asyncio.sleep(0.5)
                    
                    # Simulate occasional connection failures
                    if self.reconnect_count > 0 and self.reconnect_count % 3 == 0:
                        raise Exception("WebSocket connection failed")
                    
                    self.ws_connected = True
                    
                    self.logger.info_structured(
                        "WebSocket connected successfully",
                        stream_type="user_data",
                        reconnect_count=self.reconnect_count
                    )
                    
                    # Start message processing loop
                    asyncio.create_task(self._websocket_message_loop(correlation_id))
                    
                except Exception as e:
                    self.reconnect_count += 1
                    
                    # Record reconnection attempt
                    self.metrics.record_ws_reconnect(self.exchange_name, "user_data")
                    
                    self.logger.error_structured(
                        "WebSocket connection failed",
                        error=str(e),
                        reconnect_count=self.reconnect_count,
                        stream_type="user_data"
                    )
                    
                    # Send alert for frequent reconnections
                    if self.reconnect_count > 5:
                        await self.observability.send_custom_alert(
                            title=f"Frequent WebSocket Reconnections: {self.exchange_name}",
                            message=f"WebSocket has reconnected {self.reconnect_count} times",
                            severity=AlertSeverity.MEDIUM,
                            component="websocket",
                            exchange=self.exchange_name,
                            metadata={"reconnect_count": self.reconnect_count}
                        )
                    
                    # Retry connection
                    await asyncio.sleep(5.0)
                    await self.connect_websocket()
    
    async def _websocket_message_loop(self, correlation_id: str):
        """Process WebSocket messages with latency tracking."""
        with self.logger.with_correlation_id(correlation_id):
            
            message_count = 0
            while self.ws_connected and message_count < 10:  # Demo limit
                # Simulate message processing
                message_start = time.time()
                await asyncio.sleep(0.01)  # Processing time
                processing_delay = time.time() - message_start
                
                # Record message latency
                self.metrics.record_ws_latency(
                    self.exchange_name, 
                    "user_data", 
                    processing_delay
                )
                
                if message_count % 5 == 0:  # Log every 5th message
                    self.logger.debug_structured(
                        "WebSocket message processed",
                        message_count=message_count,
                        processing_delay_ms=processing_delay * 1000,
                        stream_type="user_data"
                    )
                
                message_count += 1
                await asyncio.sleep(1.0)  # Message interval
    
    async def update_trading_readiness(self):
        """Update trading readiness status."""
        # Check various readiness conditions
        conditions = {
            "websocket_connected": self.ws_connected,
            "api_accessible": True,  # Would check API accessibility
            "balance_sufficient": True,  # Would check balance
            "position_limits_ok": self.reconnect_count < 10  # Fail if too many reconnects
        }
        
        # Update individual component readiness
        for component, is_ready in conditions.items():
            self.metrics.set_trading_readiness(f"{self.exchange_name}_{component}", is_ready)
        
        # Overall readiness
        overall_ready = all(conditions.values())
        self.metrics.set_trading_readiness(f"{self.exchange_name}_overall", overall_ready)
        
        self.logger.info_structured(
            "Trading readiness updated",
            overall_ready=overall_ready,
            conditions=conditions
        )
        
        # Alert if not ready
        if not overall_ready:
            failed_conditions = [k for k, v in conditions.items() if not v]
            await self.observability.send_custom_alert(
                title=f"Trading Not Ready: {self.exchange_name}",
                message=f"Failed conditions: {', '.join(failed_conditions)}",
                severity=AlertSeverity.MEDIUM,
                component="trading_readiness",
                exchange=self.exchange_name,
                metadata={"failed_conditions": failed_conditions}
            )


async def demo_exchange_integration():
    """Demonstrate the observable exchange connector."""
    print("=== Observable Exchange Connector Demo ===")
    
    # Create connector
    exchange = ObservableExchangeConnector("binance")
    
    # Test account balance
    print("\n1. Testing account balance...")
    try:
        balance = await exchange.get_account_balance()
        print(f"Balance retrieved: {len(balance)} assets")
    except Exception as e:
        print(f"Balance error: {e}")
    
    # Test order placement
    print("\n2. Testing order placement...")
    try:
        order = await exchange.place_order("BTC-USDT", "buy", 0.001, 50000.0)
        print(f"Order placed: {order['order_id']}")
    except Exception as e:
        print(f"Order error: {e}")
    
    # Test order placement failure
    print("\n3. Testing order failure...")
    try:
        order = await exchange.place_order("BTC-USDT", "buy", 15.0, 50000.0)  # Large size will fail
        print(f"Order placed: {order['order_id']}")
    except Exception as e:
        print(f"Expected order error: {e}")
    
    # Test WebSocket connection
    print("\n4. Testing WebSocket connection...")
    await exchange.connect_websocket()
    
    # Wait for some messages
    await asyncio.sleep(3)
    
    # Test trading readiness
    print("\n5. Testing trading readiness...")
    await exchange.update_trading_readiness()
    
    print("\nDemo completed! Check logs and metrics for observability data.")


if __name__ == "__main__":
    # Set up demo environment
    import os
    os.environ['LOG_LEVEL'] = 'INFO'
    os.environ['JSON_LOGGING'] = 'true'
    
    # Run demo
    asyncio.run(demo_exchange_integration())