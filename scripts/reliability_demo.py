#!/usr/bin/env python3
"""
Demo script for the reliability and limits system.

This script demonstrates the key features of the reliability system:
- Rate limiting with token buckets
- Time synchronization monitoring
- Circuit breakers
- Trading readiness checks
- Health endpoints

Run with: python scripts/reliability_demo.py
"""
import asyncio
import logging
import random
import time
from typing import Dict, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import reliability components
from hummingbot.core.reliability import ReliabilityManager, ReliabilityConfig
from hummingbot.core.utils.circuit_breakers import CircuitBreakerType
from hummingbot.core.utils.trading_readiness import ConnectionStatus


class TradingSimulator:
    """Simulates trading operations to demonstrate reliability features."""
    
    def __init__(self, reliability_manager: ReliabilityManager):
        self.reliability_manager = reliability_manager
        self.trade_count = 0
        self.error_count = 0
        self.logger = logging.getLogger(__name__)
    
    async def simulate_exchange_connections(self):
        """Simulate exchange connections with various states."""
        exchanges = ["binance", "coinbase", "kraken"]
        connection_types = ["rest", "websocket", "user_stream"]
        
        while True:
            for exchange in exchanges:
                for conn_type in connection_types:
                    # Simulate connection status
                    if random.random() < 0.95:  # 95% chance of good connection
                        status = ConnectionStatus.CONNECTED
                        latency = random.uniform(10, 100)  # 10-100ms latency
                        error = ""
                    else:  # 5% chance of issues
                        status = random.choice([
                            ConnectionStatus.DISCONNECTED,
                            ConnectionStatus.ERROR,
                            ConnectionStatus.CONNECTING
                        ])
                        latency = random.uniform(100, 5000)  # Higher latency on issues
                        error = "Connection timeout" if status == ConnectionStatus.ERROR else ""
                    
                    self.reliability_manager.update_connection_status(
                        exchange, conn_type, status, latency, error
                    )
            
            await asyncio.sleep(10)  # Update every 10 seconds
    
    async def simulate_margin_updates(self):
        """Simulate margin status updates."""
        exchanges = ["binance", "coinbase", "kraken"]
        
        while True:
            for exchange in exchanges:
                # Simulate changing margin levels
                base_balance = 10000
                used_margin = random.uniform(0, base_balance * 0.8)  # Up to 80% used
                available_balance = base_balance - used_margin
                
                self.reliability_manager.update_margin_status(
                    exchange, available_balance, used_margin
                )
            
            await asyncio.sleep(15)  # Update every 15 seconds
    
    async def simulate_trading_operations(self):
        """Simulate trading operations with successes and failures."""
        exchanges = ["binance", "coinbase", "kraken"]
        
        while True:
            if not self.reliability_manager.is_trading_ready():
                self.logger.warning("Trading not ready - waiting...")
                await asyncio.sleep(5)
                continue
            
            exchange = random.choice(exchanges)
            
            # Try to acquire rate limit
            if not await self.reliability_manager.acquire_rate_limit(
                exchange, tokens=1, is_critical=True, timeout=5.0
            ):
                self.logger.warning(f"Rate limited on {exchange}")
                await asyncio.sleep(1)
                continue
            
            # Check circuit breakers
            if not self.reliability_manager.can_execute_operation(CircuitBreakerType.ERROR_SERIES):
                self.logger.warning("Error series circuit breaker open")
                await asyncio.sleep(5)
                continue
            
            # Simulate trade execution
            try:
                await self.execute_simulated_trade(exchange)
                self.trade_count += 1
                
                # Record success
                self.reliability_manager.record_success(
                    CircuitBreakerType.ERROR_SERIES,
                    {"exchange": exchange, "trade_id": self.trade_count}
                )
                
                self.logger.info(f"Trade {self.trade_count} executed successfully on {exchange}")
                
            except Exception as e:
                self.error_count += 1
                
                # Record failure
                self.reliability_manager.record_failure(
                    CircuitBreakerType.ERROR_SERIES,
                    {"exchange": exchange, "error": str(e), "trade_id": self.trade_count + 1}
                )
                
                self.logger.error(f"Trade failed on {exchange}: {e}")
            
            # Random delay between trades
            await asyncio.sleep(random.uniform(0.5, 2.0))
    
    async def execute_simulated_trade(self, exchange: str):
        """Simulate trade execution with random success/failure."""
        # Simulate API call delay
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        # Simulate failure rate (10% chance of failure)
        if random.random() < 0.1:
            raise Exception(f"Simulated API error on {exchange}")
        
        # Simulate hedge deviation failure (rare)
        if random.random() < 0.02:
            self.reliability_manager.record_failure(
                CircuitBreakerType.HEDGE_DEVIATION,
                {"exchange": exchange, "deviation": "High spread detected"}
            )
            raise Exception("Hedge deviation exceeded threshold")
        
        # Simulate order cancellation failure (very rare)
        if random.random() < 0.01:
            self.reliability_manager.record_failure(
                CircuitBreakerType.ORDER_CANCELLATION,
                {"exchange": exchange, "order_id": f"sim_{self.trade_count}"}
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trading simulation statistics."""
        return {
            "total_trades": self.trade_count,
            "total_errors": self.error_count,
            "success_rate": (self.trade_count / max(1, self.trade_count + self.error_count)) * 100
        }


async def demo_reliability_system():
    """Main demo function."""
    logger = logging.getLogger(__name__)
    logger.info("Starting reliability system demo...")
    
    # Configure reliability system
    config = ReliabilityConfig()
    config.time_sync_drift_threshold_ms = 500.0  # 500ms threshold
    config.error_series_threshold = 5  # Trip after 5 errors
    config.hedge_deviation_threshold = 3  # Trip after 3 hedge deviations
    config.readiness_check_interval = 10.0  # Check every 10 seconds
    config.health_endpoint_port = 8080
    
    reliability_manager = ReliabilityManager(config)
    
    # Configure exchange rate limits
    reliability_manager.configure_exchange_rate_limit("binance", capacity=120, refill_rate=2.0)
    reliability_manager.configure_exchange_rate_limit("coinbase", capacity=10, refill_rate=1.0)
    reliability_manager.configure_exchange_rate_limit("kraken", capacity=60, refill_rate=1.0)
    
    # Add event callbacks
    async def on_trading_halted(reason):
        logger.error(f"🚨 TRADING HALTED: {reason}")
    
    async def on_trading_resumed(reason):
        logger.info(f"✅ TRADING RESUMED: {reason}")
    
    reliability_manager.add_trading_halted_callback(on_trading_halted)
    reliability_manager.add_trading_resumed_callback(on_trading_resumed)
    
    # Create trading simulator
    simulator = TradingSimulator(reliability_manager)
    
    try:
        # Start reliability system
        await reliability_manager.start()
        logger.info("✅ Reliability system started")
        logger.info(f"🌐 Health endpoint available at: http://localhost:8080/health/ready")
        
        # Start simulation tasks
        tasks = [
            asyncio.create_task(simulator.simulate_exchange_connections()),
            asyncio.create_task(simulator.simulate_margin_updates()),
            asyncio.create_task(simulator.simulate_trading_operations()),
            asyncio.create_task(print_status_updates(reliability_manager, simulator))
        ]
        
        logger.info("🚀 Starting trading simulation...")
        logger.info("📊 Monitor status at: http://localhost:8080/health/detailed")
        
        # Run demo for specified duration or until interrupted
        await asyncio.gather(*tasks)
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    finally:
        # Stop reliability system
        await reliability_manager.stop()
        logger.info("Demo completed")


async def print_status_updates(reliability_manager: ReliabilityManager, simulator: TradingSimulator):
    """Print periodic status updates."""
    logger = logging.getLogger(__name__)
    
    while True:
        await asyncio.sleep(30)  # Print status every 30 seconds
        
        # Get comprehensive status
        status = reliability_manager.get_comprehensive_status()
        stats = simulator.get_stats()
        
        logger.info("📈 === STATUS UPDATE ===")
        logger.info(f"Overall Ready: {status['overall_ready']}")
        logger.info(f"Trades: {stats['total_trades']}, Errors: {stats['total_errors']}, Success Rate: {stats['success_rate']:.1f}%")
        
        if reliability_manager.time_sync_monitor:
            drift = reliability_manager.get_time_drift_ms()
            logger.info(f"Time Drift: {drift:.1f}ms")
        
        # Circuit breaker status
        if "circuit_breakers" in status["components"]:
            cb_status = status["components"]["circuit_breakers"]
            logger.info(f"Circuit Breakers - Can Trade: {cb_status['can_trade']}")
        
        # Rate limiter status
        if "rate_limiter" in status["components"]:
            rl_status = status["components"]["rate_limiter"]
            for exchange, info in rl_status.items():
                logger.info(f"Rate Limit {exchange}: {info['tokens_available']:.0f}/{info['capacity']} tokens")


if __name__ == "__main__":
    try:
        asyncio.run(demo_reliability_system())
    except KeyboardInterrupt:
        print("\nDemo stopped by user")
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()