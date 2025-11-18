"""
Configuration validation for funding arbitrage bot using Pydantic Settings.
Validates environment variables on startup with clear error messages.
"""

import os
from typing import List, Optional, Dict, Any
from pydantic import BaseSettings, validator, Field
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class ExchangeCredentials(BaseSettings):
    """Base class for exchange API credentials."""
    
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    passphrase: Optional[str] = None  # For exchanges like OKX, KuCoin
    testnet: bool = False

    class Config:
        case_sensitive = False


class BinanceCredentials(ExchangeCredentials):
    """Binance API credentials."""
    api_key: Optional[str] = Field(None, env="BINANCE_API_KEY")
    secret_key: Optional[str] = Field(None, env="BINANCE_SECRET_KEY")
    testnet: bool = Field(False, env="BINANCE_TESTNET")


class BinancePerpetualCredentials(ExchangeCredentials):
    """Binance Perpetual API credentials."""
    api_key: Optional[str] = Field(None, env="BINANCE_PERPETUAL_API_KEY")
    secret_key: Optional[str] = Field(None, env="BINANCE_PERPETUAL_SECRET_KEY")
    testnet: bool = Field(False, env="BINANCE_TESTNET")


class BybitCredentials(ExchangeCredentials):
    """Bybit API credentials."""
    api_key: Optional[str] = Field(None, env="BYBIT_API_KEY")
    secret_key: Optional[str] = Field(None, env="BYBIT_SECRET_KEY")
    testnet: bool = Field(False, env="BYBIT_TESTNET")


class BybitPerpetualCredentials(ExchangeCredentials):
    """Bybit Perpetual API credentials."""
    api_key: Optional[str] = Field(None, env="BYBIT_PERPETUAL_API_KEY")
    secret_key: Optional[str] = Field(None, env="BYBIT_PERPETUAL_SECRET_KEY")
    testnet: bool = Field(False, env="BYBIT_TESTNET")


class OKXCredentials(ExchangeCredentials):
    """OKX API credentials."""
    api_key: Optional[str] = Field(None, env="OKX_API_KEY")
    secret_key: Optional[str] = Field(None, env="OKX_SECRET_KEY")
    passphrase: Optional[str] = Field(None, env="OKX_PASSPHRASE")
    demo: bool = Field(False, env="OKX_DEMO")


class OKXPerpetualCredentials(ExchangeCredentials):
    """OKX Perpetual API credentials."""
    api_key: Optional[str] = Field(None, env="OKX_PERPETUAL_API_KEY")
    secret_key: Optional[str] = Field(None, env="OKX_PERPETUAL_SECRET_KEY")
    passphrase: Optional[str] = Field(None, env="OKX_PERPETUAL_PASSPHRASE")
    demo: bool = Field(False, env="OKX_DEMO")


class GateIOCredentials(ExchangeCredentials):
    """Gate.io API credentials."""
    api_key: Optional[str] = Field(None, env="GATE_IO_API_KEY")
    secret_key: Optional[str] = Field(None, env="GATE_IO_SECRET_KEY")


class GateIOPerpetualCredentials(ExchangeCredentials):
    """Gate.io Perpetual API credentials."""
    api_key: Optional[str] = Field(None, env="GATE_IO_PERPETUAL_API_KEY")
    secret_key: Optional[str] = Field(None, env="GATE_IO_PERPETUAL_SECRET_KEY")


class KuCoinCredentials(ExchangeCredentials):
    """KuCoin API credentials."""
    api_key: Optional[str] = Field(None, env="KUCOIN_API_KEY")
    secret_key: Optional[str] = Field(None, env="KUCOIN_SECRET_KEY")
    passphrase: Optional[str] = Field(None, env="KUCOIN_PASSPHRASE")


class KuCoinPerpetualCredentials(ExchangeCredentials):
    """KuCoin Perpetual API credentials."""
    api_key: Optional[str] = Field(None, env="KUCOIN_PERPETUAL_API_KEY")
    secret_key: Optional[str] = Field(None, env="KUCOIN_PERPETUAL_SECRET_KEY")
    passphrase: Optional[str] = Field(None, env="KUCOIN_PERPETUAL_PASSPHRASE")


class DatabaseConfig(BaseSettings):
    """Database configuration."""
    host: str = Field("postgres", env="POSTGRES_HOST")
    port: int = Field(5432, env="POSTGRES_PORT")
    database: str = Field("postgres", env="POSTGRES_DB")
    user: str = Field("postgres", env="POSTGRES_USER")
    password: str = Field("password", env="POSTGRES_PASSWORD")

    class Config:
        case_sensitive = False


class RiskManagementConfig(BaseSettings):
    """Risk management configuration."""
    min_funding_rate_profitability: Decimal = Field(
        Decimal("0.0005"), 
        env="MIN_FUNDING_RATE_PROFITABILITY",
        description="Minimum funding rate spread to enter positions (decimal)"
    )
    max_position_size_quote: Decimal = Field(
        Decimal("100"), 
        env="MAX_POSITION_SIZE_QUOTE",
        description="Maximum position size per exchange in quote currency"
    )
    default_leverage: int = Field(
        3, 
        env="DEFAULT_LEVERAGE",
        description="Default leverage for perpetual futures"
    )
    max_position_concentration: Decimal = Field(
        Decimal("0.2"), 
        env="MAX_POSITION_CONCENTRATION",
        description="Maximum percentage of portfolio in single asset"
    )
    stop_loss_percentage: Decimal = Field(
        Decimal("0.02"), 
        env="STOP_LOSS_PERCENTAGE",
        description="Stop loss percentage for individual positions"
    )
    max_concurrent_positions: int = Field(
        5, 
        env="MAX_CONCURRENT_POSITIONS",
        description="Maximum number of simultaneous positions"
    )

    @validator('min_funding_rate_profitability', 'max_position_concentration', 'stop_loss_percentage')
    def validate_percentage(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Percentage values must be between 0 and 1")
        return v

    @validator('default_leverage')
    def validate_leverage(cls, v):
        if v < 1 or v > 100:
            raise ValueError("Leverage must be between 1 and 100")
        return v

    @validator('max_concurrent_positions')
    def validate_max_positions(cls, v):
        if v < 1:
            raise ValueError("Maximum concurrent positions must be at least 1")
        return v

    class Config:
        case_sensitive = False


class TimingConfig(BaseSettings):
    """Strategy timing configuration."""
    funding_rate_check_interval: int = Field(
        300, 
        env="FUNDING_RATE_CHECK_INTERVAL",
        description="How often to check funding rates (seconds)"
    )
    position_rebalance_interval: int = Field(
        3600, 
        env="POSITION_REBALANCE_INTERVAL",
        description="How often to rebalance positions (seconds)"
    )
    order_timeout: int = Field(
        30, 
        env="ORDER_TIMEOUT",
        description="Order execution timeout (seconds)"
    )
    max_funding_rate_age: int = Field(
        900, 
        env="MAX_FUNDING_RATE_AGE",
        description="Maximum age of funding rate data (seconds)"
    )

    @validator('funding_rate_check_interval', 'position_rebalance_interval', 'order_timeout', 'max_funding_rate_age')
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("Time intervals must be positive")
        return v

    class Config:
        case_sensitive = False


class NetworkConfig(BaseSettings):
    """Network and connectivity configuration."""
    http_proxy: Optional[str] = Field(None, env="HTTP_PROXY")
    https_proxy: Optional[str] = Field(None, env="HTTPS_PROXY")
    connection_timeout: int = Field(10, env="CONNECTION_TIMEOUT")
    api_rate_limit: int = Field(10, env="API_RATE_LIMIT")

    @validator('connection_timeout', 'api_rate_limit')
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError("Network settings must be positive")
        return v

    class Config:
        case_sensitive = False


class LoggingConfig(BaseSettings):
    """Logging and monitoring configuration."""
    log_level: str = Field("INFO", env="LOG_LEVEL")
    health_port: int = Field(5723, env="HEALTH_PORT")
    enable_metrics: bool = Field(True, env="ENABLE_METRICS")
    metrics_interval: int = Field(60, env="METRICS_INTERVAL")

    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    @validator('health_port')
    def validate_port(cls, v):
        if v < 1 or v > 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    class Config:
        case_sensitive = False


class FundingArbitrageConfig(BaseSettings):
    """Main configuration class for funding arbitrage bot."""
    
    # Exchange credentials
    binance: BinanceCredentials = BinanceCredentials()
    binance_perpetual: BinancePerpetualCredentials = BinancePerpetualCredentials()
    bybit: BybitCredentials = BybitCredentials()
    bybit_perpetual: BybitPerpetualCredentials = BybitPerpetualCredentials()
    okx: OKXCredentials = OKXCredentials()
    okx_perpetual: OKXPerpetualCredentials = OKXPerpetualCredentials()
    gate_io: GateIOCredentials = GateIOCredentials()
    gate_io_perpetual: GateIOPerpetualCredentials = GateIOPerpetualCredentials()
    kucoin: KuCoinCredentials = KuCoinCredentials()
    kucoin_perpetual: KuCoinPerpetualCredentials = KuCoinPerpetualCredentials()
    
    # Configuration sections
    database: DatabaseConfig = DatabaseConfig()
    risk: RiskManagementConfig = RiskManagementConfig()
    timing: TimingConfig = TimingConfig()
    network: NetworkConfig = NetworkConfig()
    logging: LoggingConfig = LoggingConfig()
    
    # Trading mode
    paper_trading_mode: bool = Field(False, env="PAPER_TRADING_MODE")
    paper_trading_balance: Decimal = Field(Decimal("10000"), env="PAPER_TRADING_BALANCE")
    
    # Feature flags
    enable_experimental_features: bool = Field(False, env="ENABLE_EXPERIMENTAL_FEATURES")
    debug_mode: bool = Field(False, env="DEBUG_MODE")

    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"

    def validate_exchange_connectivity(self) -> Dict[str, List[str]]:
        """
        Validate that at least one exchange pair is properly configured.
        Returns dict of missing credentials by exchange.
        """
        missing_credentials = {}
        
        exchanges = {
            'binance': self.binance,
            'binance_perpetual': self.binance_perpetual,
            'bybit': self.bybit,
            'bybit_perpetual': self.bybit_perpetual,
            'okx': self.okx,
            'okx_perpetual': self.okx_perpetual,
            'gate_io': self.gate_io,
            'gate_io_perpetual': self.gate_io_perpetual,
            'kucoin': self.kucoin,
            'kucoin_perpetual': self.kucoin_perpetual,
        }
        
        for exchange_name, credentials in exchanges.items():
            missing = []
            if not credentials.api_key:
                missing.append('api_key')
            if not credentials.secret_key:
                missing.append('secret_key')
            if hasattr(credentials, 'passphrase') and exchange_name in ['okx', 'okx_perpetual', 'kucoin', 'kucoin_perpetual']:
                if not credentials.passphrase:
                    missing.append('passphrase')
            
            if missing:
                missing_credentials[exchange_name] = missing
        
        return missing_credentials

    def get_configured_exchanges(self) -> List[str]:
        """Get list of exchanges with complete credentials."""
        missing = self.validate_exchange_connectivity()
        all_exchanges = [
            'binance', 'binance_perpetual', 'bybit', 'bybit_perpetual',
            'okx', 'okx_perpetual', 'gate_io', 'gate_io_perpetual',
            'kucoin', 'kucoin_perpetual'
        ]
        return [ex for ex in all_exchanges if ex not in missing]

    def validate_trading_requirements(self) -> List[str]:
        """
        Validate minimum requirements for trading.
        Returns list of validation errors.
        """
        errors = []
        
        # Check that at least one exchange pair is configured
        configured_exchanges = self.get_configured_exchanges()
        if len(configured_exchanges) < 2:
            errors.append(
                f"At least 2 exchanges must be configured for arbitrage. "
                f"Currently configured: {len(configured_exchanges)}"
            )
        
        # Check that we have both spot and perpetual exchanges if possible
        spot_exchanges = [ex for ex in configured_exchanges if 'perpetual' not in ex]
        perp_exchanges = [ex for ex in configured_exchanges if 'perpetual' in ex]
        
        if not perp_exchanges:
            errors.append("At least one perpetual exchange must be configured")
        
        # Validate position sizing
        if self.risk.max_position_size_quote <= 0:
            errors.append("Maximum position size must be greater than 0")
        
        # Validate timing parameters
        if self.timing.funding_rate_check_interval < 60:
            errors.append("Funding rate check interval should be at least 60 seconds")
        
        return errors


def load_and_validate_config() -> FundingArbitrageConfig:
    """
    Load and validate the funding arbitrage configuration.
    Raises clear errors if configuration is invalid.
    """
    try:
        config = FundingArbitrageConfig()
        
        # Validate trading requirements
        errors = config.validate_trading_requirements()
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_msg)
        
        # Log configured exchanges
        configured_exchanges = config.get_configured_exchanges()
        logger.info(f"Successfully loaded configuration with {len(configured_exchanges)} exchanges: {configured_exchanges}")
        
        # Warn about missing exchange credentials
        missing_creds = config.validate_exchange_connectivity()
        if missing_creds:
            logger.warning("Some exchanges are missing credentials:")
            for exchange, missing in missing_creds.items():
                logger.warning(f"  {exchange}: missing {missing}")
        
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise


# Global configuration instance
_config: Optional[FundingArbitrageConfig] = None


def get_config() -> FundingArbitrageConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_and_validate_config()
    return _config


def reload_config() -> FundingArbitrageConfig:
    """Reload the configuration from environment variables."""
    global _config
    _config = None
    return get_config()


if __name__ == "__main__":
    # Test configuration loading
    try:
        config = load_and_validate_config()
        print("✅ Configuration loaded successfully!")
        print(f"Configured exchanges: {config.get_configured_exchanges()}")
        print(f"Paper trading mode: {config.paper_trading_mode}")
        print(f"Risk parameters: min_funding_rate={config.risk.min_funding_rate_profitability}, max_size={config.risk.max_position_size_quote}")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        exit(1)