"""
Global circuit breakers for trading system reliability.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from hummingbot.logger import HummingbotLogger


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    ERROR_SERIES = "error_series"
    HEDGE_DEVIATION = "hedge_deviation"
    ORDER_CANCELLATION = "order_cancellation"
    POSITION_RISK = "position_risk"
    LIQUIDITY = "liquidity"


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Breaker tripped, blocking operations
    HALF_OPEN = "half_open"  # Testing if issue is resolved


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker."""
    breaker_type: CircuitBreakerType
    failure_threshold: int = 5  # Number of failures to trip
    success_threshold: int = 3  # Number of successes to close from half-open
    timeout_seconds: float = 60.0  # Time before trying half-open
    window_seconds: float = 300.0  # Time window for failure counting
    enabled: bool = True


@dataclass
class CircuitBreakerEvent:
    """Event logged by circuit breaker."""
    timestamp: float = field(default_factory=time.time)
    event_type: str = ""  # "failure", "success", "trip", "reset"
    details: Dict[str, Any] = field(default_factory=dict)


class CircuitBreaker:
    """
    Individual circuit breaker implementation.

    Monitors failures and trips when threshold is exceeded to prevent
    cascading failures and protect system integrity.
    """

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self,
                 config: CircuitBreakerConfig,
                 on_trip: Optional[Callable] = None,
                 on_reset: Optional[Callable] = None):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
            on_trip: Callback when breaker trips
            on_reset: Callback when breaker resets
        """
        self.config = config
        self.on_trip = on_trip
        self.on_reset = on_reset

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.trip_time = 0.0

        self.events: List[CircuitBreakerEvent] = []
        self._max_events = 1000

    def _log_event(self, event_type: str, details: Dict[str, Any] = None):
        """Log circuit breaker event."""
        event = CircuitBreakerEvent(
            event_type=event_type,
            details=details or {}
        )
        self.events.append(event)

        # Keep only recent events
        if len(self.events) > self._max_events:
            self.events = self.events[-self._max_events:]

    def _clean_old_failures(self):
        """Remove failures outside the time window."""
        current_time = time.time()
        cutoff_time = current_time - self.config.window_seconds

        # Count only recent failures
        recent_events = [
            e for e in self.events
            if e.timestamp > cutoff_time and e.event_type == "failure"
        ]
        self.failure_count = len(recent_events)

    def record_success(self, details: Dict[str, Any] = None):
        """Record a successful operation."""
        if not self.config.enabled:
            return

        self._log_event("success", details)

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._reset_breaker()
        elif self.state == CircuitBreakerState.CLOSED:
            # Reset failure count on success
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self, details: Dict[str, Any] = None):
        """Record a failed operation."""
        if not self.config.enabled:
            return

        self._log_event("failure", details)
        current_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failure in half-open state trips breaker again
            self._trip_breaker()
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            self.last_failure_time = current_time
            self._clean_old_failures()

            if self.failure_count >= self.config.failure_threshold:
                self._trip_breaker()

    def _trip_breaker(self):
        """Trip the circuit breaker."""
        if self.state == CircuitBreakerState.OPEN:
            return

        self.state = CircuitBreakerState.OPEN
        self.trip_time = time.time()
        self.success_count = 0

        self._log_event("trip", {
            "failure_count": self.failure_count,
            "threshold": self.config.failure_threshold
        })

        self.logger().error(
            f"Circuit breaker TRIPPED: {self.config.breaker_type.value} "
            f"({self.failure_count} failures >= {self.config.failure_threshold} threshold)"
        )

        if self.on_trip:
            try:
                asyncio.create_task(self._call_async_callback(self.on_trip))
            except Exception as e:
                self.logger().error(f"Error in trip callback: {e}")

    def _reset_breaker(self):
        """Reset the circuit breaker to closed state."""
        old_state = self.state
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0

        self._log_event("reset", {"previous_state": old_state.value})

        self.logger().info(
            f"Circuit breaker RESET: {self.config.breaker_type.value} "
            f"({self.success_count} successes >= {self.config.success_threshold} threshold)"
        )

        if self.on_reset:
            try:
                asyncio.create_task(self._call_async_callback(self.on_reset))
            except Exception as e:
                self.logger().error(f"Error in reset callback: {e}")

    async def _call_async_callback(self, callback):
        """Call async callback safely."""
        if asyncio.iscoroutinefunction(callback):
            await callback(self)
        else:
            callback(self)

    def can_execute(self) -> bool:
        """Check if operations can be executed through this breaker."""
        if not self.config.enabled:
            return True

        current_time = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            # Check if timeout has passed to try half-open
            if current_time - self.trip_time >= self.config.timeout_seconds:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                self.logger().info(
                    f"Circuit breaker entering HALF-OPEN state: {self.config.breaker_type.value}"
                )
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True

        return False

    def get_status(self) -> Dict[str, Any]:
        """Get current status of circuit breaker."""
        return {
            "type": self.config.breaker_type.value,
            "state": self.state.value,
            "enabled": self.config.enabled,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "failure_threshold": self.config.failure_threshold,
            "success_threshold": self.config.success_threshold,
            "last_failure_time": self.last_failure_time,
            "trip_time": self.trip_time,
            "can_execute": self.can_execute()
        }


class CircuitBreakerManager:
    """
    Manager for all circuit breakers in the trading system.

    Coordinates multiple circuit breakers and provides global kill switch functionality.
    """

    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger

    def __init__(self, global_kill_switch_callback: Optional[Callable] = None):
        """
        Initialize circuit breaker manager.

        Args:
            global_kill_switch_callback: Callback for global kill switch
        """
        self.breakers: Dict[CircuitBreakerType, CircuitBreaker] = {}
        self.global_kill_switch_callback = global_kill_switch_callback
        self._global_kill_switch_active = False

        # Initialize default circuit breakers
        self._initialize_default_breakers()

    def _initialize_default_breakers(self):
        """Initialize default circuit breakers."""

        # Error series breaker
        error_config = CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.ERROR_SERIES,
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=60.0,
            window_seconds=300.0
        )
        self.add_breaker(error_config, self._on_error_series_trip)

        # Hedge deviation breaker
        hedge_config = CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.HEDGE_DEVIATION,
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=30.0,
            window_seconds=120.0
        )
        self.add_breaker(hedge_config, self._on_hedge_deviation_trip)

        # Order cancellation breaker
        cancel_config = CircuitBreakerConfig(
            breaker_type=CircuitBreakerType.ORDER_CANCELLATION,
            failure_threshold=10,
            success_threshold=5,
            timeout_seconds=120.0,
            window_seconds=600.0
        )
        self.add_breaker(cancel_config, self._on_order_cancellation_trip)

    def add_breaker(self,
                   config: CircuitBreakerConfig,
                   on_trip: Optional[Callable] = None,
                   on_reset: Optional[Callable] = None):
        """Add a circuit breaker."""
        breaker = CircuitBreaker(config, on_trip, on_reset)
        self.breakers[config.breaker_type] = breaker
        self.logger().info(f"Added circuit breaker: {config.breaker_type.value}")

    def record_success(self,
                      breaker_type: CircuitBreakerType,
                      details: Dict[str, Any] = None):
        """Record success for specific breaker type."""
        if breaker_type in self.breakers:
            self.breakers[breaker_type].record_success(details)

    def record_failure(self,
                      breaker_type: CircuitBreakerType,
                      details: Dict[str, Any] = None):
        """Record failure for specific breaker type."""
        if breaker_type in self.breakers:
            self.breakers[breaker_type].record_failure(details)

    def can_execute(self, breaker_type: CircuitBreakerType) -> bool:
        """Check if operation can execute for specific breaker type."""
        if self._global_kill_switch_active:
            return False

        if breaker_type in self.breakers:
            return self.breakers[breaker_type].can_execute()

        return True

    def can_trade(self) -> bool:
        """Check if trading is allowed (all critical breakers must be closed)."""
        if self._global_kill_switch_active:
            return False

        critical_breakers = [
            CircuitBreakerType.ERROR_SERIES,
            CircuitBreakerType.HEDGE_DEVIATION,
            CircuitBreakerType.ORDER_CANCELLATION
        ]

        for breaker_type in critical_breakers:
            if not self.can_execute(breaker_type):
                return False

        return True

    def activate_global_kill_switch(self, reason: str = "Manual trigger"):
        """Activate global kill switch."""
        self._global_kill_switch_active = True
        self.logger().error(f"GLOBAL KILL SWITCH ACTIVATED: {reason}")

        if self.global_kill_switch_callback:
            try:
                asyncio.create_task(self._call_async_callback(self.global_kill_switch_callback, reason))
            except Exception as e:
                self.logger().error(f"Error in global kill switch callback: {e}")

    def deactivate_global_kill_switch(self):
        """Deactivate global kill switch."""
        self._global_kill_switch_active = False
        self.logger().info("Global kill switch deactivated")

    async def _call_async_callback(self, callback, *args):
        """Call async callback safely."""
        if asyncio.iscoroutinefunction(callback):
            await callback(*args)
        else:
            callback(*args)

    async def _on_error_series_trip(self, breaker: CircuitBreaker):
        """Handle error series circuit breaker trip."""
        self.logger().error("Error series circuit breaker tripped - considering global kill switch")
        # Could activate global kill switch if errors are too severe

    async def _on_hedge_deviation_trip(self, breaker: CircuitBreaker):
        """Handle hedge deviation circuit breaker trip."""
        self.logger().error("Hedge deviation circuit breaker tripped - halting trading")
        self.activate_global_kill_switch("Hedge deviation exceeded threshold")

    async def _on_order_cancellation_trip(self, breaker: CircuitBreaker):
        """Handle order cancellation circuit breaker trip."""
        self.logger().error("Order cancellation circuit breaker tripped")
        # Might need to activate global kill switch if cancellations are failing

    def get_all_statuses(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        return {
            "global_kill_switch_active": self._global_kill_switch_active,
            "can_trade": self.can_trade(),
            "breakers": {
                breaker_type.value: breaker.get_status()
                for breaker_type, breaker in self.breakers.items()
            }
        }

    def reset_all_breakers(self):
        """Reset all circuit breakers (emergency function)."""
        for breaker in self.breakers.values():
            if breaker.state != CircuitBreakerState.CLOSED:
                breaker.state = CircuitBreakerState.CLOSED
                breaker.failure_count = 0
                breaker.success_count = 0

        self.logger().warning("All circuit breakers forcefully reset")

    def configure_breaker(self,
                         breaker_type: CircuitBreakerType,
                         **config_updates):
        """Update configuration for specific breaker."""
        if breaker_type in self.breakers:
            breaker = self.breakers[breaker_type]
            for key, value in config_updates.items():
                if hasattr(breaker.config, key):
                    setattr(breaker.config, key, value)
                    self.logger().info(
                        f"Updated {breaker_type.value} breaker config: {key}={value}"
                    )