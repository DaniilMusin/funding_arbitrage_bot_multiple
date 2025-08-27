"""
Trading readiness and health check system.
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any

from hummingbot.logger import HummingbotLogger


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ConnectionStatus(Enum):
    """Connection status types."""
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    name: str
    status: HealthStatus
    message: str
    details: Dict[str, Any]
    timestamp: float
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class ConnectionHealth:
    """Health information for a connection."""
    exchange: str
    connection_type: str  # "rest", "websocket", "user_stream"
    status: ConnectionStatus
    last_seen: float
    latency_ms: float = 0.0
    error_count: int = 0
    last_error: str = ""


@dataclass
class MarginHealth:
    """Margin and risk health information."""
    exchange: str
    available_balance: float
    used_margin: float
    margin_ratio: float
    free_margin: float
    currency: str
    warning_threshold: float = 0.8
    critical_threshold: float = 0.95


class TradingReadinessChecker:
    """
    Trading readiness and health check system.
    
    Monitors:
    - Exchange connections (REST, WebSocket, user streams)
    - Margin levels and available balance
    - System resources and performance
    - External dependencies
    """
    
    _logger: Optional[HummingbotLogger] = None
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    def __init__(self, 
                 check_interval: float = 30.0,
                 connection_timeout: float = 60.0):
        """
        Initialize trading readiness checker.
        
        Args:
            check_interval: Interval between health checks
            connection_timeout: Timeout for considering connection stale
        """
        self.check_interval = check_interval
        self.connection_timeout = connection_timeout
        
        self._monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Health state
        self.connections: Dict[str, ConnectionHealth] = {}
        self.margins: Dict[str, MarginHealth] = {}
        self.health_checks: List[HealthCheckResult] = []
        self._max_health_history = 100
        
        # Readiness state
        self._is_ready = False
        self._ready_callbacks: List[Callable] = []
        self._not_ready_callbacks: List[Callable] = []
        
        # Custom health check functions
        self._custom_checks: Dict[str, Callable] = {}
    
    def add_ready_callback(self, callback: Callable):
        """Add callback for when system becomes ready."""
        self._ready_callbacks.append(callback)
    
    def add_not_ready_callback(self, callback: Callable):
        """Add callback for when system becomes not ready."""
        self._not_ready_callbacks.append(callback)
    
    def register_custom_check(self, name: str, check_func: Callable):
        """Register custom health check function."""
        self._custom_checks[name] = check_func
    
    def update_connection_status(self, 
                               exchange: str,
                               connection_type: str,
                               status: ConnectionStatus,
                               latency_ms: float = 0.0,
                               error: str = ""):
        """Update connection status."""
        key = f"{exchange}_{connection_type}"
        
        if key not in self.connections:
            self.connections[key] = ConnectionHealth(
                exchange=exchange,
                connection_type=connection_type,
                status=status,
                last_seen=time.time()
            )
        
        connection = self.connections[key]
        connection.status = status
        connection.last_seen = time.time()
        connection.latency_ms = latency_ms
        
        if error:
            connection.error_count += 1
            connection.last_error = error
        elif status == ConnectionStatus.CONNECTED:
            connection.error_count = 0
            connection.last_error = ""
    
    def update_margin_status(self, 
                           exchange: str,
                           available_balance: float,
                           used_margin: float,
                           currency: str = "USD"):
        """Update margin status for exchange."""
        total_balance = available_balance + used_margin
        margin_ratio = used_margin / total_balance if total_balance > 0 else 0
        
        self.margins[exchange] = MarginHealth(
            exchange=exchange,
            available_balance=available_balance,
            used_margin=used_margin,
            margin_ratio=margin_ratio,
            free_margin=available_balance,
            currency=currency
        )
    
    def check_connections_health(self) -> HealthCheckResult:
        """Check health of all connections."""
        current_time = time.time()
        critical_issues = []
        warning_issues = []
        healthy_connections = 0
        
        for key, conn in self.connections.items():
            # Check if connection is stale
            time_since_seen = current_time - conn.last_seen
            
            if time_since_seen > self.connection_timeout:
                critical_issues.append(f"{key}: stale ({time_since_seen:.1f}s ago)")
            elif conn.status == ConnectionStatus.ERROR:
                critical_issues.append(f"{key}: error - {conn.last_error}")
            elif conn.status == ConnectionStatus.DISCONNECTED:
                warning_issues.append(f"{key}: disconnected")
            elif conn.status == ConnectionStatus.CONNECTING:
                warning_issues.append(f"{key}: connecting")
            elif conn.latency_ms > 5000:  # High latency
                warning_issues.append(f"{key}: high latency ({conn.latency_ms:.1f}ms)")
            else:
                healthy_connections += 1
        
        if critical_issues:
            status = HealthStatus.CRITICAL
            message = f"Critical connection issues: {'; '.join(critical_issues)}"
        elif warning_issues:
            status = HealthStatus.WARNING
            message = f"Connection warnings: {'; '.join(warning_issues)}"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {healthy_connections} connections healthy"
        
        return HealthCheckResult(
            name="connections",
            status=status,
            message=message,
            details={
                "healthy_count": healthy_connections,
                "warning_count": len(warning_issues),
                "critical_count": len(critical_issues),
                "total_connections": len(self.connections)
            },
            timestamp=current_time
        )
    
    def check_margins_health(self) -> HealthCheckResult:
        """Check health of margin levels."""
        critical_issues = []
        warning_issues = []
        healthy_margins = 0
        
        for exchange, margin in self.margins.items():
            if margin.margin_ratio >= margin.critical_threshold:
                critical_issues.append(
                    f"{exchange}: critical margin ratio {margin.margin_ratio:.2%}"
                )
            elif margin.margin_ratio >= margin.warning_threshold:
                warning_issues.append(
                    f"{exchange}: high margin ratio {margin.margin_ratio:.2%}"
                )
            elif margin.available_balance <= 0:
                critical_issues.append(f"{exchange}: no available balance")
            else:
                healthy_margins += 1
        
        if critical_issues:
            status = HealthStatus.CRITICAL
            message = f"Critical margin issues: {'; '.join(critical_issues)}"
        elif warning_issues:
            status = HealthStatus.WARNING
            message = f"Margin warnings: {'; '.join(warning_issues)}"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {healthy_margins} margin levels healthy"
        
        return HealthCheckResult(
            name="margins",
            status=status,
            message=message,
            details={
                "healthy_count": healthy_margins,
                "warning_count": len(warning_issues),
                "critical_count": len(critical_issues),
                "total_exchanges": len(self.margins)
            },
            timestamp=time.time()
        )
    
    def check_system_resources(self) -> HealthCheckResult:
        """Check system resource health."""
        try:
            import psutil
            
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Check memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            issues = []
            if cpu_percent > 90:
                issues.append(f"high CPU usage ({cpu_percent:.1f}%)")
            if memory_percent > 90:
                issues.append(f"high memory usage ({memory_percent:.1f}%)")
            if disk_percent > 95:
                issues.append(f"high disk usage ({disk_percent:.1f}%)")
            
            if issues:
                status = HealthStatus.WARNING if cpu_percent < 95 else HealthStatus.CRITICAL
                message = f"System resource issues: {'; '.join(issues)}"
            else:
                status = HealthStatus.HEALTHY
                message = f"System resources healthy (CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%, Disk: {disk_percent:.1f}%)"
            
            return HealthCheckResult(
                name="system_resources",
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "disk_percent": disk_percent
                },
                timestamp=time.time()
            )
            
        except ImportError:
            return HealthCheckResult(
                name="system_resources",
                status=HealthStatus.UNKNOWN,
                message="psutil not available - cannot check system resources",
                details={},
                timestamp=time.time()
            )
        except Exception as e:
            return HealthCheckResult(
                name="system_resources",
                status=HealthStatus.WARNING,
                message=f"Error checking system resources: {e}",
                details={"error": str(e)},
                timestamp=time.time()
            )
    
    async def run_custom_checks(self) -> List[HealthCheckResult]:
        """Run all custom health checks."""
        results = []
        
        for name, check_func in self._custom_checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    result = await check_func()
                else:
                    result = check_func()
                
                if isinstance(result, HealthCheckResult):
                    results.append(result)
                else:
                    # Assume it returns (status, message, details)
                    status, message, details = result
                    results.append(HealthCheckResult(
                        name=name,
                        status=status,
                        message=message,
                        details=details,
                        timestamp=time.time()
                    ))
            except Exception as e:
                results.append(HealthCheckResult(
                    name=name,
                    status=HealthStatus.CRITICAL,
                    message=f"Health check failed: {e}",
                    details={"error": str(e)},
                    timestamp=time.time()
                ))
        
        return results
    
    async def run_all_checks(self) -> List[HealthCheckResult]:
        """Run all health checks."""
        results = []
        
        # Core health checks
        results.append(self.check_connections_health())
        results.append(self.check_margins_health())
        results.append(self.check_system_resources())
        
        # Custom health checks
        custom_results = await self.run_custom_checks()
        results.extend(custom_results)
        
        # Store results
        self.health_checks.extend(results)
        if len(self.health_checks) > self._max_health_history:
            self.health_checks = self.health_checks[-self._max_health_history:]
        
        return results
    
    def is_trading_ready(self) -> bool:
        """Check if system is ready for trading."""
        if not self.health_checks:
            return False
        
        # Get latest health check results
        latest_checks = {}
        for check in reversed(self.health_checks):
            if check.name not in latest_checks:
                latest_checks[check.name] = check
        
        # Check critical systems
        critical_systems = ["connections", "margins"]
        
        for system in critical_systems:
            if system not in latest_checks:
                return False
            
            if latest_checks[system].status == HealthStatus.CRITICAL:
                return False
        
        return True
    
    async def _update_readiness_state(self):
        """Update readiness state and trigger callbacks."""
        new_ready_state = self.is_trading_ready()
        
        if new_ready_state != self._is_ready:
            old_state = self._is_ready
            self._is_ready = new_ready_state
            
            self.logger().info(
                f"Trading readiness changed: {old_state} -> {new_ready_state}"
            )
            
            # Trigger callbacks
            callbacks = self._ready_callbacks if new_ready_state else self._not_ready_callbacks
            for callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(new_ready_state)
                    else:
                        callback(new_ready_state)
                except Exception as e:
                    self.logger().error(f"Error in readiness callback: {e}")
    
    async def _monitor_loop(self):
        """Main monitoring loop."""
        self.logger().info(f"Starting trading readiness monitoring (interval: {self.check_interval}s)")
        
        while self._monitoring:
            try:
                await self.run_all_checks()
                await self._update_readiness_state()
            except Exception as e:
                self.logger().error(f"Error in readiness monitoring: {e}", exc_info=True)
            
            await asyncio.sleep(self.check_interval)
    
    def start_monitoring(self):
        """Start readiness monitoring."""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self.logger().info("Trading readiness monitoring started")
    
    def stop_monitoring(self):
        """Stop readiness monitoring."""
        if not self._monitoring:
            return
        
        self._monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
        
        self.logger().info("Trading readiness monitoring stopped")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        if not self.health_checks:
            return {
                "overall_status": HealthStatus.UNKNOWN.value,
                "is_ready": False,
                "message": "No health checks performed yet"
            }
        
        # Get latest results for each check type
        latest_checks = {}
        for check in reversed(self.health_checks):
            if check.name not in latest_checks:
                latest_checks[check.name] = check
        
        # Determine overall status
        has_critical = any(c.status == HealthStatus.CRITICAL for c in latest_checks.values())
        has_warning = any(c.status == HealthStatus.WARNING for c in latest_checks.values())
        
        if has_critical:
            overall_status = HealthStatus.CRITICAL
        elif has_warning:
            overall_status = HealthStatus.WARNING
        else:
            overall_status = HealthStatus.HEALTHY
        
        return {
            "overall_status": overall_status.value,
            "is_ready": self._is_ready,
            "last_check": max(c.timestamp for c in latest_checks.values()) if latest_checks else 0,
            "checks": {
                name: {
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                    "timestamp": check.timestamp
                }
                for name, check in latest_checks.items()
            },
            "connections": {
                key: {
                    "exchange": conn.exchange,
                    "type": conn.connection_type,
                    "status": conn.status.value,
                    "latency_ms": conn.latency_ms,
                    "last_seen": conn.last_seen,
                    "error_count": conn.error_count
                }
                for key, conn in self.connections.items()
            },
            "margins": {
                exchange: {
                    "available_balance": margin.available_balance,
                    "used_margin": margin.used_margin,
                    "margin_ratio": margin.margin_ratio,
                    "currency": margin.currency
                }
                for exchange, margin in self.margins.items()
            }
        }
    
    @property
    def is_ready(self) -> bool:
        """Check if trading is ready."""
        return self._is_ready