"""
Reliability Manager - Unified coordinator for all reliability and limits features.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable

from hummingbot.core.api_throttler.token_bucket_rate_limiter import EnhancedRateLimiter
from hummingbot.core.utils.time_sync_monitor import TimeSyncMonitor
from hummingbot.core.utils.circuit_breakers import (
    CircuitBreakerManager,
    CircuitBreakerType,
    CircuitBreakerConfig
)
from hummingbot.core.utils.trading_readiness import (
    TradingReadinessChecker,
    ConnectionStatus,
    HealthStatus
)
from hummingbot.core.api.health_endpoint import HealthEndpointManager
from hummingbot.logger import HummingbotLogger


class ReliabilityConfig:
    """Configuration for reliability manager."""

    def __init__(self):
        # Time sync configuration
        self.time_sync_enabled = True
        self.time_sync_drift_threshold_ms = 1000.0
        self.time_sync_check_interval = 60.0

        # Circuit breaker configuration
        self.circuit_breakers_enabled = True
        self.error_series_threshold = 5
        self.hedge_deviation_threshold = 3
        self.order_cancellation_threshold = 10

        # Trading readiness configuration
        self.readiness_check_enabled = True
        self.readiness_check_interval = 30.0
        self.connection_timeout = 60.0

        # Rate limiting configuration
        self.rate_limiting_enabled = True
        self.default_rate_capacity = 100
        self.default_rate_refill = 10.0

        # Health endpoint configuration
        self.health_endpoint_enabled = True
        self.health_endpoint_port = 8080
        self.health_endpoint_host = "127.0.0.1"


class ReliabilityManager:
    """
    Unified reliability manager coordinating all reliability and limits features.

    Components:
    - Enhanced rate limiting with token buckets per exchange
    - NTP time synchronization monitoring with drift detection
    - Circuit breakers for error series, hedge deviation, and order cancellation
    - Trading readiness health checks for connections and margins
    - Health endpoint for system status monitoring
    """

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, config: ReliabilityConfig = None):
        """
        Initialize reliability manager.

        Args:
            config: Reliability configuration
        """
        self.config = config or ReliabilityConfig()

        # Core components
        self.rate_limiter: Optional[EnhancedRateLimiter] = None
        self.time_sync_monitor: Optional[TimeSyncMonitor] = None
        self.circuit_breaker_manager: Optional[CircuitBreakerManager] = None
        self.trading_readiness_checker: Optional[TradingReadinessChecker] = None
        self.health_endpoint_manager: Optional[HealthEndpointManager] = None

        # State
        self._initialized = False
        self._running = False

        # Event callbacks
        self._trading_halted_callbacks: List[Callable] = []
        self._trading_resumed_callbacks: List[Callable] = []

    async def initialize(self):
        """Initialize all reliability components."""
        if self._initialized:
            return

        self.logger().info("Initializing reliability manager...")

        try:
            # Initialize rate limiter
            if self.config.rate_limiting_enabled:
                self.rate_limiter = EnhancedRateLimiter()
                self.logger().info("Enhanced rate limiter initialized")

            # Initialize time sync monitor
            if self.config.time_sync_enabled:
                self.time_sync_monitor = TimeSyncMonitor(
                    drift_threshold_ms=self.config.time_sync_drift_threshold_ms,
                    check_interval=self.config.time_sync_check_interval,
                    on_drift_exceeded=self._on_time_drift_exceeded
                )
                self.logger().info("Time sync monitor initialized")

            # Initialize circuit breaker manager
            if self.config.circuit_breakers_enabled:
                self.circuit_breaker_manager = CircuitBreakerManager(
                    global_kill_switch_callback=self._on_global_kill_switch
                )

                # Configure custom thresholds
                self.circuit_breaker_manager.configure_breaker(
                    CircuitBreakerType.ERROR_SERIES,
                    failure_threshold=self.config.error_series_threshold
                )
                self.circuit_breaker_manager.configure_breaker(
                    CircuitBreakerType.HEDGE_DEVIATION,
                    failure_threshold=self.config.hedge_deviation_threshold
                )
                self.circuit_breaker_manager.configure_breaker(
                    CircuitBreakerType.ORDER_CANCELLATION,
                    failure_threshold=self.config.order_cancellation_threshold
                )

                self.logger().info("Circuit breaker manager initialized")

            # Initialize trading readiness checker
            if self.config.readiness_check_enabled:
                self.trading_readiness_checker = TradingReadinessChecker(
                    check_interval=self.config.readiness_check_interval,
                    connection_timeout=self.config.connection_timeout
                )

                # Add readiness callbacks
                self.trading_readiness_checker.add_ready_callback(self._on_trading_ready)
                self.trading_readiness_checker.add_not_ready_callback(self._on_trading_not_ready)

                self.logger().info("Trading readiness checker initialized")

            # Initialize health endpoint
            if self.config.health_endpoint_enabled:
                endpoint_config = {
                    "port": self.config.health_endpoint_port,
                    "host": self.config.health_endpoint_host
                }
                self.health_endpoint_manager = HealthEndpointManager(endpoint_config)

                # Register components with health endpoint
                if self.time_sync_monitor:
                    self.health_endpoint_manager.register_component(
                        "time_sync_monitor", self.time_sync_monitor
                    )
                if self.circuit_breaker_manager:
                    self.health_endpoint_manager.register_component(
                        "circuit_breaker_manager", self.circuit_breaker_manager
                    )
                if self.trading_readiness_checker:
                    self.health_endpoint_manager.register_component(
                        "trading_readiness_checker", self.trading_readiness_checker
                    )
                if self.rate_limiter:
                    self.health_endpoint_manager.register_component(
                        "rate_limiter", self.rate_limiter
                    )

                self.logger().info("Health endpoint manager initialized")

            self._initialized = True
            self.logger().info("Reliability manager initialization completed")

        except Exception as e:
            self.logger().error(f"Failed to initialize reliability manager: {e}")
            raise

    async def start(self):
        """Start all reliability monitoring."""
        if not self._initialized:
            await self.initialize()

        if self._running:
            return

        self.logger().info("Starting reliability monitoring...")

        try:
            # Start time sync monitoring
            if self.time_sync_monitor:
                self.time_sync_monitor.start_monitoring()

            # Start trading readiness monitoring
            if self.trading_readiness_checker:
                self.trading_readiness_checker.start_monitoring()

            # Start health endpoint
            if self.health_endpoint_manager:
                await self.health_endpoint_manager.start()

            self._running = True
            self.logger().info("Reliability monitoring started")

        except Exception as e:
            self.logger().error(f"Failed to start reliability monitoring: {e}")
            raise

    async def stop(self):
        """Stop all reliability monitoring."""
        if not self._running:
            return

        self.logger().info("Stopping reliability monitoring...")

        try:
            # Stop time sync monitoring
            if self.time_sync_monitor:
                self.time_sync_monitor.stop_monitoring()

            # Stop trading readiness monitoring
            if self.trading_readiness_checker:
                self.trading_readiness_checker.stop_monitoring()

            # Stop health endpoint
            if self.health_endpoint_manager:
                await self.health_endpoint_manager.stop()

            self._running = False
            self.logger().info("Reliability monitoring stopped")

        except Exception as e:
            self.logger().error(f"Error stopping reliability monitoring: {e}")

    # Rate limiting methods
    async def acquire_rate_limit(self,
                               exchange: str,
                               tokens: int = 1,
                               is_critical: bool = False,
                               timeout: float = 60.0) -> bool:
        """Acquire rate limit tokens for exchange."""
        if not self.rate_limiter:
            return True

        return await self.rate_limiter.wait_for_tokens(
            exchange, tokens, is_critical, timeout
        )

    def configure_exchange_rate_limit(self,
                                    exchange: str,
                                    capacity: int,
                                    refill_rate: float):
        """Configure rate limits for specific exchange."""
        if self.rate_limiter:
            self.rate_limiter.configure_exchange(exchange, capacity, refill_rate)

    # Time sync methods
    def is_time_sync_ok(self) -> bool:
        """Check if time synchronization is acceptable."""
        if not self.time_sync_monitor:
            return True
        return self.time_sync_monitor.is_trading_allowed

    def get_time_drift_ms(self) -> float:
        """Get current time drift in milliseconds."""
        if not self.time_sync_monitor:
            return 0.0
        return self.time_sync_monitor.current_drift_ms

    # Circuit breaker methods
    def record_success(self,
                      breaker_type: CircuitBreakerType,
                      details: Dict[str, Any] = None):
        """Record successful operation for circuit breaker."""
        if self.circuit_breaker_manager:
            self.circuit_breaker_manager.record_success(breaker_type, details)

    def record_failure(self,
                      breaker_type: CircuitBreakerType,
                      details: Dict[str, Any] = None):
        """Record failed operation for circuit breaker."""
        if self.circuit_breaker_manager:
            self.circuit_breaker_manager.record_failure(breaker_type, details)

    def can_execute_operation(self, breaker_type: CircuitBreakerType) -> bool:
        """Check if operation can be executed through circuit breaker."""
        if not self.circuit_breaker_manager:
            return True
        return self.circuit_breaker_manager.can_execute(breaker_type)

    def activate_kill_switch(self, reason: str = "Manual trigger"):
        """Activate global kill switch."""
        if self.circuit_breaker_manager:
            self.circuit_breaker_manager.activate_global_kill_switch(reason)

    # Trading readiness methods
    def update_connection_status(self,
                               exchange: str,
                               connection_type: str,
                               status: ConnectionStatus,
                               latency_ms: float = 0.0,
                               error: str = ""):
        """Update connection status for readiness monitoring."""
        if self.trading_readiness_checker:
            self.trading_readiness_checker.update_connection_status(
                exchange, connection_type, status, latency_ms, error
            )

    def update_margin_status(self,
                           exchange: str,
                           available_balance: float,
                           used_margin: float,
                           currency: str = "USD"):
        """Update margin status for readiness monitoring."""
        if self.trading_readiness_checker:
            self.trading_readiness_checker.update_margin_status(
                exchange, available_balance, used_margin, currency
            )

    def is_trading_ready(self) -> bool:
        """Check if system is ready for trading."""
        # Check all critical systems
        checks = [
            self.is_time_sync_ok(),
            self.circuit_breaker_manager.can_trade() if self.circuit_breaker_manager else True,
            self.trading_readiness_checker.is_ready if self.trading_readiness_checker else True
        ]

        return all(checks)

    def can_trade(self) -> (bool, str):
        """Return readiness boolean with reason string for blocks."""
        if not self.is_time_sync_ok():
            return False, "time_drift"
        if self.circuit_breaker_manager and not self.circuit_breaker_manager.can_trade():
            return False, "circuit_breaker"
        if self.trading_readiness_checker:
            ready, reason = self.trading_readiness_checker.can_trade()
            if not ready:
                return False, reason
        return True, "ok"

    def can_pass_rate_limit(self, exchange: str, tokens_needed: int = 1) -> bool:
        """Non-blocking check if enough rate-limit tokens are immediately available."""
        if not self.rate_limiter:
            return True
        status = self.rate_limiter.get_bucket_status(exchange)
        return status.get("tokens_available", 0) >= tokens_needed

    # Event callbacks
    def add_trading_halted_callback(self, callback: Callable):
        """Add callback for when trading is halted."""
        self._trading_halted_callbacks.append(callback)

    def add_trading_resumed_callback(self, callback: Callable):
        """Add callback for when trading is resumed."""
        self._trading_resumed_callbacks.append(callback)

    async def _on_time_drift_exceeded(self, drift_ms: float):
        """Handle time drift exceeded event."""
        self.logger().error(f"Time drift exceeded threshold: {drift_ms:.1f}ms")
        await self._notify_trading_halted("time_drift_exceeded")

    async def _on_global_kill_switch(self, reason: str):
        """Handle global kill switch activation."""
        self.logger().error(f"Global kill switch activated: {reason}")
        await self._notify_trading_halted("global_kill_switch")

    async def _on_trading_ready(self, is_ready: bool):
        """Handle trading readiness change to ready."""
        if is_ready:
            self.logger().info("System is ready for trading")
            await self._notify_trading_resumed("readiness_restored")

    async def _on_trading_not_ready(self, is_ready: bool):
        """Handle trading readiness change to not ready."""
        if not is_ready:
            self.logger().warning("System is not ready for trading")
            await self._notify_trading_halted("readiness_failed")

    async def _notify_trading_halted(self, reason: str):
        """Notify that trading has been halted."""
        for callback in self._trading_halted_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason)
                else:
                    callback(reason)
            except Exception as e:
                self.logger().error(f"Error in trading halted callback: {e}")

    async def _notify_trading_resumed(self, reason: str):
        """Notify that trading has been resumed."""
        for callback in self._trading_resumed_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(reason)
                else:
                    callback(reason)
            except Exception as e:
                self.logger().error(f"Error in trading resumed callback: {e}")

    # Status and monitoring
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all reliability components."""
        status = {
            "timestamp": asyncio.get_event_loop().time(),
            "overall_ready": self.is_trading_ready(),
            "running": self._running,
            "components": {}
        }

        # Rate limiter status
        if self.rate_limiter:
            status["components"]["rate_limiter"] = self.rate_limiter.get_all_statuses()

        # Time sync status
        if self.time_sync_monitor:
            status["components"]["time_sync"] = {
                "is_trading_allowed": self.time_sync_monitor.is_trading_allowed,
                "current_drift_ms": self.time_sync_monitor.current_drift_ms,
                "statistics": self.time_sync_monitor.get_drift_statistics()
            }

        # Circuit breaker status
        if self.circuit_breaker_manager:
            status["components"]["circuit_breakers"] = self.circuit_breaker_manager.get_all_statuses()

        # Trading readiness status
        if self.trading_readiness_checker:
            status["components"]["trading_readiness"] = self.trading_readiness_checker.get_health_summary()

        return status

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()