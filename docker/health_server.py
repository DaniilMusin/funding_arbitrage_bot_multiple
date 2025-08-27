import os
import sys
import time
import logging
import psutil
import asyncio
import aiohttp
from flask import Flask, jsonify
from datetime import datetime, timezone
from typing import Dict, Any, List

# Add hummingbot path for configuration access
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'hummingbot'))

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global variables for caching health status
_last_readiness_check = 0
_readiness_cache = {'status': 'unknown', 'checks': {}}
_cache_ttl = 30  # Cache readiness for 30 seconds


class HealthChecker:
    """Health checker for funding arbitrage bot."""
    
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=5)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_exchange_connectivity(self) -> Dict[str, Any]:
        """Check connectivity to key exchanges."""
        exchanges = {
            'binance': 'https://api.binance.com/api/v3/time',
            'bybit': 'https://api.bybit.com/v5/market/time',
            'okx': 'https://www.okx.com/api/v5/public/time'
        }
        
        results = {}
        for exchange, url in exchanges.items():
            try:
                start_time = time.time()
                async with self.session.get(url) as response:
                    latency = (time.time() - start_time) * 1000
                    if response.status == 200:
                        results[exchange] = {
                            'status': 'healthy',
                            'latency_ms': round(latency, 2)
                        }
                    else:
                        results[exchange] = {
                            'status': 'unhealthy',
                            'error': f'HTTP {response.status}'
                        }
            except Exception as e:
                results[exchange] = {
                    'status': 'unhealthy',
                    'error': str(e)
                }
        
        return results
    
    async def check_database_connectivity(self) -> Dict[str, Any]:
        """Check database connectivity."""
        try:
            import psycopg2
            
            # Get database config from environment
            db_config = {
                'host': os.getenv('POSTGRES_HOST', 'postgres'),
                'port': os.getenv('POSTGRES_PORT', '5432'),
                'database': os.getenv('POSTGRES_DB', 'postgres'),
                'user': os.getenv('POSTGRES_USER', 'postgres'),
                'password': os.getenv('POSTGRES_PASSWORD', 'password')
            }
            
            # Test connection
            conn = psycopg2.connect(**db_config)
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            cursor.close()
            conn.close()
            
            return {'status': 'healthy', 'message': 'Database connection successful'}
            
        except ImportError:
            return {'status': 'warning', 'message': 'psycopg2 not available, skipping database check'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}
    
    def check_configuration(self) -> Dict[str, Any]:
        """Check configuration validity."""
        try:
            from hummingbot.client.config.funding_arbitrage_config import load_and_validate_config
            
            config = load_and_validate_config()
            configured_exchanges = config.get_configured_exchanges()
            validation_errors = config.validate_trading_requirements()
            
            if validation_errors:
                return {
                    'status': 'unhealthy',
                    'errors': validation_errors,
                    'configured_exchanges': len(configured_exchanges)
                }
            else:
                return {
                    'status': 'healthy',
                    'configured_exchanges': len(configured_exchanges),
                    'exchanges': configured_exchanges
                }
                
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': f'Configuration validation failed: {str(e)}'
            }
    
    def check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine health based on thresholds
            status = 'healthy'
            warnings = []
            
            if cpu_percent > 90:
                status = 'unhealthy'
                warnings.append(f'High CPU usage: {cpu_percent}%')
            elif cpu_percent > 70:
                warnings.append(f'Moderate CPU usage: {cpu_percent}%')
            
            if memory.percent > 90:
                status = 'unhealthy'
                warnings.append(f'High memory usage: {memory.percent}%')
            elif memory.percent > 70:
                warnings.append(f'Moderate memory usage: {memory.percent}%')
            
            if disk.percent > 95:
                status = 'unhealthy'
                warnings.append(f'High disk usage: {disk.percent}%')
            elif disk.percent > 80:
                warnings.append(f'Moderate disk usage: {disk.percent}%')
            
            return {
                'status': status if not warnings or status == 'unhealthy' else 'warning',
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'disk_percent': disk.percent,
                'warnings': warnings
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }


async def perform_readiness_check() -> Dict[str, Any]:
    """Perform comprehensive readiness check."""
    checker = HealthChecker()
    
    checks = {}
    overall_status = 'healthy'
    
    # Check system resources
    checks['system'] = checker.check_system_resources()
    if checks['system']['status'] == 'unhealthy':
        overall_status = 'unhealthy'
    
    # Check configuration
    checks['configuration'] = checker.check_configuration()
    if checks['configuration']['status'] == 'unhealthy':
        overall_status = 'unhealthy'
    
    # Check database connectivity
    checks['database'] = await checker.check_database_connectivity()
    if checks['database']['status'] == 'unhealthy':
        overall_status = 'unhealthy'
    
    # Check exchange connectivity
    async with checker:
        checks['exchanges'] = await checker.check_exchange_connectivity()
        
        # At least 2 exchanges should be healthy for trading
        healthy_exchanges = sum(1 for ex_data in checks['exchanges'].values() if ex_data['status'] == 'healthy')
        if healthy_exchanges < 2:
            overall_status = 'unhealthy'
            checks['exchanges']['_summary'] = f'Only {healthy_exchanges} exchanges healthy, need at least 2'
    
    return {
        'status': overall_status,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'checks': checks
    }


@app.route('/health/liveness')
def liveness():
    """
    Kubernetes liveness probe endpoint.
    Returns 200 if the process is alive and responding.
    """
    return jsonify({
        'status': 'alive',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'pid': os.getpid()
    }), 200


@app.route('/health/readiness')
def readiness():
    """
    Kubernetes readiness probe endpoint.
    Returns 200 if the service is ready to handle trading requests.
    """
    global _last_readiness_check, _readiness_cache, _cache_ttl
    
    current_time = time.time()
    
    # Use cached result if recent
    if current_time - _last_readiness_check < _cache_ttl:
        status_code = 200 if _readiness_cache['status'] == 'healthy' else 503
        return jsonify(_readiness_cache), status_code
    
    # Perform new readiness check
    try:
        # Run async check in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(perform_readiness_check())
        loop.close()
        
        _readiness_cache = result
        _last_readiness_check = current_time
        
        status_code = 200 if result['status'] == 'healthy' else 503
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        error_result = {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        return jsonify(error_result), 503


@app.route('/livez')
def livez():
    """Legacy liveness endpoint for backward compatibility."""
    return 'alive', 200


@app.route('/metrics')
def metrics():
    """Detailed metrics endpoint."""
    try:
        data = {
            'cpu_percent': psutil.cpu_percent(interval=0.1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_percent': psutil.disk_usage('/').percent,
            'process_count': len(psutil.pids()),
            'boot_time': psutil.boot_time(),
            'timestamp': time.time(),
        }
        
        # Add load average on Unix systems
        try:
            load_avg = os.getloadavg()
            data['load_average'] = {
                '1min': load_avg[0],
                '5min': load_avg[1],
                '15min': load_avg[2]
            }
        except (OSError, AttributeError):
            # Windows doesn't have getloadavg
            pass
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
@app.route('/')
def health():
    """General health endpoint with summary information."""
    try:
        # Get basic system info
        system_info = {
            'status': 'healthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': time.time() - psutil.boot_time(),
            'process_pid': os.getpid()
        }
        
        # Quick system check
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent
        
        if cpu_percent > 90 or memory_percent > 90:
            system_info['status'] = 'degraded'
            system_info['warnings'] = []
            if cpu_percent > 90:
                system_info['warnings'].append(f'High CPU: {cpu_percent}%')
            if memory_percent > 90:
                system_info['warnings'].append(f'High memory: {memory_percent}%')
        
        return jsonify(system_info)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500


if __name__ == '__main__':
    port = int(os.getenv('HEALTH_PORT', '5723'))
    debug = os.getenv('DEBUG_MODE', 'false').lower() == 'true'
    
    logger.info(f"Starting enhanced health server on port {port}")
    logger.info("Available endpoints:")
    logger.info("  /health/liveness  - Kubernetes liveness probe")
    logger.info("  /health/readiness - Kubernetes readiness probe") 
    logger.info("  /metrics         - Detailed system metrics")
    logger.info("  /health          - General health summary")
    logger.info("  /livez           - Legacy liveness endpoint")
    
    app.run(host='0.0.0.0', port=port, debug=debug)