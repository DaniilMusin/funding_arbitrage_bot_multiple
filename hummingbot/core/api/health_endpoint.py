"""
Health endpoint for system status monitoring.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional

from aiohttp import web, hdrs
from aiohttp.web import Request, Response

from hummingbot.logger import HummingbotLogger


class HealthEndpoint:
    """
    HTTP endpoint for health and readiness checks.
    
    Provides REST API endpoints for monitoring system health:
    - /health/live - liveness probe
    - /health/ready - readiness probe  
    - /health/status - detailed health status
    """
    
    _logger: Optional[HummingbotLogger] = None
    
    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = logging.getLogger(__name__)
        return cls._logger
    
    def __init__(self, 
                 port: int = 8080,
                 host: str = "127.0.0.1"):
        """
        Initialize health endpoint.
        
        Args:
            port: Port to listen on
            host: Host to bind to
        """
        self.port = port
        self.host = host
        
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        # Health dependencies
        self.time_sync_monitor = None
        self.circuit_breaker_manager = None
        self.trading_readiness_checker = None
        self.rate_limiter = None
        
        # Setup routes
        self._setup_routes()
        
        # Service info
        self.start_time = time.time()
        self.version = "1.0.0"
    
    def _setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get('/health/live', self.liveness_handler)
        self.app.router.add_get('/health/ready', self.readiness_handler)
        self.app.router.add_get('/health/status', self.status_handler)
        self.app.router.add_get('/health/detailed', self.detailed_status_handler)
        
        # CORS headers for all routes
        self.app.middlewares.append(self._cors_middleware)
    
    async def _cors_middleware(self, request: Request, handler):
        """Add CORS headers to all responses."""
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    def set_dependencies(self, 
                        time_sync_monitor=None,
                        circuit_breaker_manager=None,
                        trading_readiness_checker=None,
                        rate_limiter=None):
        """Set health check dependencies."""
        self.time_sync_monitor = time_sync_monitor
        self.circuit_breaker_manager = circuit_breaker_manager
        self.trading_readiness_checker = trading_readiness_checker
        self.rate_limiter = rate_limiter
    
    async def liveness_handler(self, request: Request) -> Response:
        """
        Liveness probe endpoint.
        
        Returns 200 if the service is alive and responding.
        """
        try:
            uptime = time.time() - self.start_time
            
            response_data = {
                "status": "alive",
                "timestamp": time.time(),
                "uptime_seconds": uptime,
                "version": self.version
            }
            
            return web.json_response(response_data, status=200)
            
        except Exception as e:
            self.logger().error(f"Error in liveness check: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, 
                status=500
            )
    
    async def readiness_handler(self, request: Request) -> Response:
        """
        Readiness probe endpoint.
        
        Returns 200 if the service is ready to handle traffic.
        """
        try:
            ready = True
            issues = []
            
            # Check time synchronization
            if self.time_sync_monitor:
                if not self.time_sync_monitor.is_trading_allowed:
                    ready = False
                    issues.append(f"Time sync issue: {self.time_sync_monitor.current_drift_ms:.1f}ms drift")
            
            # Check circuit breakers
            if self.circuit_breaker_manager:
                if not self.circuit_breaker_manager.can_trade():
                    ready = False
                    breaker_statuses = self.circuit_breaker_manager.get_all_statuses()
                    for breaker_type, status in breaker_statuses["breakers"].items():
                        if not status["can_execute"]:
                            issues.append(f"Circuit breaker tripped: {breaker_type}")
            
            # Check trading readiness
            if self.trading_readiness_checker:
                if not self.trading_readiness_checker.is_ready:
                    ready = False
                    issues.append("Trading readiness checks failed")
            
            if ready:
                return web.json_response({
                    "status": "ready",
                    "timestamp": time.time(),
                    "message": "All systems ready"
                }, status=200)
            else:
                return web.json_response({
                    "status": "not_ready",
                    "timestamp": time.time(),
                    "issues": issues
                }, status=503)
                
        except Exception as e:
            self.logger().error(f"Error in readiness check: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, 
                status=500
            )
    
    async def status_handler(self, request: Request) -> Response:
        """
        Basic status endpoint.
        
        Returns summary status information.
        """
        try:
            status_data = {
                "timestamp": time.time(),
                "uptime_seconds": time.time() - self.start_time,
                "version": self.version,
                "components": {}
            }
            
            # Time sync status
            if self.time_sync_monitor:
                status_data["components"]["time_sync"] = {
                    "healthy": self.time_sync_monitor.is_trading_allowed,
                    "drift_ms": self.time_sync_monitor.current_drift_ms
                }
            
            # Circuit breaker status
            if self.circuit_breaker_manager:
                breaker_statuses = self.circuit_breaker_manager.get_all_statuses()
                status_data["components"]["circuit_breakers"] = {
                    "healthy": breaker_statuses["can_trade"],
                    "global_kill_switch": breaker_statuses["global_kill_switch_active"]
                }
            
            # Trading readiness status
            if self.trading_readiness_checker:
                status_data["components"]["trading_readiness"] = {
                    "healthy": self.trading_readiness_checker.is_ready
                }
            
            return web.json_response(status_data, status=200)
            
        except Exception as e:
            self.logger().error(f"Error in status check: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, 
                status=500
            )
    
    async def detailed_status_handler(self, request: Request) -> Response:
        """
        Detailed status endpoint.
        
        Returns comprehensive system status information.
        """
        try:
            detailed_data = {
                "timestamp": time.time(),
                "uptime_seconds": time.time() - self.start_time,
                "version": self.version,
                "service_info": {
                    "host": self.host,
                    "port": self.port,
                    "start_time": self.start_time
                }
            }
            
            # Time sync detailed status
            if self.time_sync_monitor:
                detailed_data["time_sync"] = {
                    "is_trading_allowed": self.time_sync_monitor.is_trading_allowed,
                    "current_drift_ms": self.time_sync_monitor.current_drift_ms,
                    "drift_threshold_ms": self.time_sync_monitor.drift_threshold_ms,
                    "statistics": self.time_sync_monitor.get_drift_statistics()
                }
            
            # Circuit breaker detailed status
            if self.circuit_breaker_manager:
                detailed_data["circuit_breakers"] = self.circuit_breaker_manager.get_all_statuses()
            
            # Trading readiness detailed status
            if self.trading_readiness_checker:
                detailed_data["trading_readiness"] = self.trading_readiness_checker.get_health_summary()
            
            # Rate limiter status
            if self.rate_limiter and hasattr(self.rate_limiter, 'get_all_statuses'):
                detailed_data["rate_limiting"] = self.rate_limiter.get_all_statuses()
            
            return web.json_response(detailed_data, status=200)
            
        except Exception as e:
            self.logger().error(f"Error in detailed status check: {e}")
            return web.json_response(
                {"status": "error", "message": str(e)}, 
                status=500
            )
    
    async def start(self):
        """Start the health endpoint server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            self.logger().info(f"Health endpoint started on http://{self.host}:{self.port}")
            
        except Exception as e:
            self.logger().error(f"Failed to start health endpoint: {e}")
            raise
    
    async def stop(self):
        """Stop the health endpoint server."""
        try:
            if self.site:
                await self.site.stop()
            
            if self.runner:
                await self.runner.cleanup()
            
            self.logger().info("Health endpoint stopped")
            
        except Exception as e:
            self.logger().error(f"Error stopping health endpoint: {e}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()


class HealthEndpointManager:
    """
    Manager for health endpoint with automatic dependency injection.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize health endpoint manager.
        
        Args:
            config: Configuration dictionary
        """
        config = config or {}
        
        self.endpoint = HealthEndpoint(
            port=config.get("port", 8080),
            host=config.get("host", "127.0.0.1")
        )
        
        # Will be set by system components
        self._components = {}
    
    def register_component(self, name: str, component):
        """Register a system component for health monitoring."""
        self._components[name] = component
        
        # Update endpoint dependencies
        self.endpoint.set_dependencies(
            time_sync_monitor=self._components.get("time_sync_monitor"),
            circuit_breaker_manager=self._components.get("circuit_breaker_manager"),
            trading_readiness_checker=self._components.get("trading_readiness_checker"),
            rate_limiter=self._components.get("rate_limiter")
        )
    
    async def start(self):
        """Start health endpoint."""
        await self.endpoint.start()
    
    async def stop(self):
        """Stop health endpoint."""
        await self.endpoint.stop()
    
    def get_health_url(self, endpoint_type: str = "ready") -> str:
        """Get URL for specific health endpoint."""
        base_url = f"http://{self.endpoint.host}:{self.endpoint.port}"
        return f"{base_url}/health/{endpoint_type}"