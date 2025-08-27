"""
Example configuration for the reliability and limits system.

This file shows how to configure the various components of the reliability system
for different trading environments and requirements.
"""
from hummingbot.core.reliability import ReliabilityConfig


def create_production_config() -> ReliabilityConfig:
    """Create production-grade reliability configuration."""
    config = ReliabilityConfig()
    
    # Time synchronization - strict for production
    config.time_sync_enabled = True
    config.time_sync_drift_threshold_ms = 250.0  # 250ms maximum drift
    config.time_sync_check_interval = 30.0  # Check every 30 seconds
    
    # Circuit breakers - conservative thresholds
    config.circuit_breakers_enabled = True
    config.error_series_threshold = 3  # Trip after 3 consecutive errors
    config.hedge_deviation_threshold = 2  # Trip after 2 hedge deviations
    config.order_cancellation_threshold = 5  # Trip after 5 cancellation failures
    
    # Trading readiness - frequent checks
    config.readiness_check_enabled = True
    config.readiness_check_interval = 15.0  # Check every 15 seconds
    config.connection_timeout = 30.0  # 30 second connection timeout
    
    # Rate limiting - production limits
    config.rate_limiting_enabled = True
    config.default_rate_capacity = 100
    config.default_rate_refill = 5.0  # Conservative refill rate
    
    # Health endpoint - internal monitoring
    config.health_endpoint_enabled = True
    config.health_endpoint_port = 8080
    config.health_endpoint_host = "127.0.0.1"  # Internal only
    
    return config


def create_development_config() -> ReliabilityConfig:
    """Create development-friendly reliability configuration."""
    config = ReliabilityConfig()
    
    # Time synchronization - relaxed for development
    config.time_sync_enabled = True
    config.time_sync_drift_threshold_ms = 1000.0  # 1 second drift allowed
    config.time_sync_check_interval = 120.0  # Check every 2 minutes
    
    # Circuit breakers - higher thresholds for development
    config.circuit_breakers_enabled = True
    config.error_series_threshold = 10  # More forgiving
    config.hedge_deviation_threshold = 5
    config.order_cancellation_threshold = 15
    
    # Trading readiness - less frequent checks
    config.readiness_check_enabled = True
    config.readiness_check_interval = 60.0  # Check every minute
    config.connection_timeout = 120.0  # 2 minute timeout
    
    # Rate limiting - higher limits for development
    config.rate_limiting_enabled = True
    config.default_rate_capacity = 200
    config.default_rate_refill = 20.0  # Higher refill rate
    
    # Health endpoint - accessible for debugging
    config.health_endpoint_enabled = True
    config.health_endpoint_port = 8080
    config.health_endpoint_host = "0.0.0.0"  # Accessible from outside
    
    return config


def create_testing_config() -> ReliabilityConfig:
    """Create configuration for testing environments."""
    config = ReliabilityConfig()
    
    # Time synchronization - disabled for testing
    config.time_sync_enabled = False
    
    # Circuit breakers - very high thresholds
    config.circuit_breakers_enabled = True
    config.error_series_threshold = 50
    config.hedge_deviation_threshold = 20
    config.order_cancellation_threshold = 50
    
    # Trading readiness - fast checks for testing
    config.readiness_check_enabled = True
    config.readiness_check_interval = 5.0  # Fast checks
    config.connection_timeout = 10.0  # Short timeout
    
    # Rate limiting - very permissive for testing
    config.rate_limiting_enabled = True
    config.default_rate_capacity = 1000
    config.default_rate_refill = 100.0
    
    # Health endpoint - disabled for testing
    config.health_endpoint_enabled = False
    
    return config


def create_high_frequency_config() -> ReliabilityConfig:
    """Create configuration optimized for high-frequency trading."""
    config = ReliabilityConfig()
    
    # Time synchronization - very strict
    config.time_sync_enabled = True
    config.time_sync_drift_threshold_ms = 50.0  # 50ms maximum drift
    config.time_sync_check_interval = 10.0  # Check every 10 seconds
    
    # Circuit breakers - very sensitive
    config.circuit_breakers_enabled = True
    config.error_series_threshold = 2  # Trip immediately on errors
    config.hedge_deviation_threshold = 1  # No tolerance for hedge deviation
    config.order_cancellation_threshold = 3
    
    # Trading readiness - continuous monitoring
    config.readiness_check_enabled = True
    config.readiness_check_interval = 5.0  # Check every 5 seconds
    config.connection_timeout = 15.0  # Short timeout
    
    # Rate limiting - high capacity, fast refill
    config.rate_limiting_enabled = True
    config.default_rate_capacity = 500
    config.default_rate_refill = 50.0
    
    # Health endpoint - enabled for monitoring
    config.health_endpoint_enabled = True
    config.health_endpoint_port = 8080
    config.health_endpoint_host = "127.0.0.1"
    
    return config


# Exchange-specific rate limiting configurations
EXCHANGE_RATE_LIMITS = {
    # Major exchanges with high limits
    "binance": {
        "spot": {"capacity": 1200, "refill_rate": 20.0},
        "futures": {"capacity": 2400, "refill_rate": 40.0}
    },
    "coinbase": {
        "spot": {"capacity": 100, "refill_rate": 10.0}
    },
    "kraken": {
        "spot": {"capacity": 60, "refill_rate": 1.0}
    },
    "okx": {
        "spot": {"capacity": 300, "refill_rate": 5.0},
        "futures": {"capacity": 600, "refill_rate": 10.0}
    },
    "bybit": {
        "spot": {"capacity": 600, "refill_rate": 10.0},
        "futures": {"capacity": 1200, "refill_rate": 20.0}
    },
    
    # Smaller exchanges with conservative limits
    "gate_io": {
        "spot": {"capacity": 200, "refill_rate": 5.0}
    },
    "kucoin": {
        "spot": {"capacity": 300, "refill_rate": 5.0}
    },
    "mexc": {
        "spot": {"capacity": 200, "refill_rate": 5.0}
    },
    "bitmart": {
        "spot": {"capacity": 150, "refill_rate": 3.0}
    }
}


def apply_exchange_rate_limits(reliability_manager, environment="production"):
    """Apply exchange-specific rate limits to reliability manager."""
    
    # Adjust limits based on environment
    multiplier = {
        "production": 1.0,
        "development": 2.0,  # Higher limits for development
        "testing": 10.0,     # Very high limits for testing
        "high_frequency": 1.5  # Slightly higher for HFT
    }.get(environment, 1.0)
    
    for exchange, configs in EXCHANGE_RATE_LIMITS.items():
        for market_type, limits in configs.items():
            exchange_key = f"{exchange}_{market_type}" if market_type != "spot" else exchange
            
            capacity = int(limits["capacity"] * multiplier)
            refill_rate = limits["refill_rate"] * multiplier
            
            reliability_manager.configure_exchange_rate_limit(
                exchange_key, capacity, refill_rate
            )


# Example usage
def setup_reliability_for_environment(environment="production"):
    """Setup reliability manager for specific environment."""
    from hummingbot.core.reliability import ReliabilityManager
    
    # Get configuration for environment
    config_functions = {
        "production": create_production_config,
        "development": create_development_config,
        "testing": create_testing_config,
        "high_frequency": create_high_frequency_config
    }
    
    config_func = config_functions.get(environment, create_production_config)
    config = config_func()
    
    # Create reliability manager
    reliability_manager = ReliabilityManager(config)
    
    # Apply exchange-specific rate limits
    apply_exchange_rate_limits(reliability_manager, environment)
    
    return reliability_manager


# Configuration validation
def validate_config(config: ReliabilityConfig) -> list:
    """Validate reliability configuration and return warnings."""
    warnings = []
    
    if config.time_sync_drift_threshold_ms > 1000:
        warnings.append("Time sync drift threshold > 1000ms may be too permissive for trading")
    
    if config.error_series_threshold > 10:
        warnings.append("Error series threshold > 10 may allow too many failures")
    
    if config.readiness_check_interval > 120:
        warnings.append("Readiness check interval > 2 minutes may be too slow")
    
    if config.default_rate_refill < 1.0:
        warnings.append("Rate limiter refill < 1.0 tokens/sec may be too restrictive")
    
    return warnings