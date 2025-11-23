import os
from decimal import Decimal
from typing import Dict, List, Set

import pandas as pd
from pydantic import Field, field_validator

from hummingbot.client.ui.interface_utils import format_df_for_printout
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.clock import Clock
from hummingbot.core.data_type.common import OrderType, PositionAction, PositionMode, PriceType, TradeType
from hummingbot.core.event.events import FundingPaymentCompletedEvent
from hummingbot.data_feed.candles_feed.data_types import CandlesConfig
from hummingbot.strategy.strategy_v2_base import StrategyV2Base, StrategyV2ConfigBase
from hummingbot.strategy_v2.executors.position_executor.data_types import PositionExecutorConfig, TripleBarrierConfig
from hummingbot.strategy_v2.models.executor_actions import CreateExecutorAction, StopExecutorAction

# Critical production utilities
from utils import TelegramAlerter, get_rate_limiter


class FundingRateArbitrageConfig(StrategyV2ConfigBase):
    script_file_name: str = os.path.basename(__file__)
    candles_config: List[CandlesConfig] = []
    controllers_config: List[str] = []
    markets: Dict[str, Set[str]] = {}
    leverage: int = Field(
        default=20, gt=0,
        json_schema_extra={"prompt": lambda mi: "Enter the leverage (e.g. 20): ", "prompt_on_new": True},
    )
    min_funding_rate_profitability: Decimal = Field(
        default=0.001,
        json_schema_extra={
            "prompt": lambda mi: "Enter the min funding rate profitability to enter in a position (e.g. 0.001): ",
            "prompt_on_new": True}
    )
    connectors: Set[str] = Field(
        default="okx_perpetual,bybit_perpetual,hyperliquid_perpetual",
        json_schema_extra={
            "prompt": lambda mi: "Enter the connectors separated by commas (e.g. okx_perpetual,bybit_perpetual,hyperliquid_perpetual): ",
            "prompt_on_new": True}
    )
    tokens: Set[str] = Field(
        default="WIF,FET",
        json_schema_extra={"prompt": lambda mi: "Enter the tokens separated by commas (e.g. WIF,FET): ", "prompt_on_new": True},
    )
    position_size_quote: Decimal = Field(
        default=100,
        json_schema_extra={
            "prompt": lambda mi: "Enter the position size in quote asset (e.g. order amount 100 will open 100 long on connector1 and 100 short on connector2): ",
            "prompt_on_new": True
        }
    )
    profitability_to_take_profit: Decimal = Field(
        default=0.01,
        json_schema_extra={
            "prompt": lambda mi: "Enter the profitability to take profit (including PNL of positions and fundings received): ",
            "prompt_on_new": True}
    )
    funding_rate_diff_stop_loss: Decimal = Field(
        default=-0.001,
        json_schema_extra={
            "prompt": lambda mi: "Enter the funding rate difference to stop the position (e.g. -0.001): ",
            "prompt_on_new": True}
    )
    trade_profitability_condition_to_enter: bool = Field(
        default=False,
        json_schema_extra={
            "prompt": lambda mi: "Do you want to check the trade profitability condition to enter? (True/False): ",
            "prompt_on_new": True}
    )
    max_slippage_pct: Decimal = Field(
        default=0.005,
        json_schema_extra={
            "prompt": lambda mi: "Enter the maximum allowed slippage percentage (e.g. 0.005 for 0.5%): ",
            "prompt_on_new": False}
    )
    position_validation_enabled: bool = Field(
        default=True,
        json_schema_extra={
            "prompt": lambda mi: "Enable position validation after opening? (True/False): ",
            "prompt_on_new": False}
    )
    emergency_close_on_imbalance: bool = Field(
        default=True,
        json_schema_extra={
            "prompt": lambda mi: "Enable emergency close if hedge is imbalanced? (True/False): ",
            "prompt_on_new": False}
    )
    max_position_imbalance_pct: Decimal = Field(
        default=0.10,
        json_schema_extra={
            "prompt": lambda mi: "Enter max position imbalance percentage before emergency close (e.g. 0.10 for 10%): ",
            "prompt_on_new": False}
    )
    min_time_to_next_funding_seconds: int = Field(
        default=300,
        json_schema_extra={
            "prompt": lambda mi: "Enter minimum time to next funding settlement in seconds (e.g. 300 for 5 min): ",
            "prompt_on_new": False}
    )
    min_order_book_depth_multiplier: Decimal = Field(
        default=Decimal("3.0"),
        json_schema_extra={
            "prompt": lambda mi: "Enter minimum order book depth multiplier (e.g. 3.0 means 3x position size): ",
            "prompt_on_new": False}
    )
    check_order_book_depth_enabled: bool = Field(
        default=True,
        json_schema_extra={
            "prompt": lambda mi: "Enable order book depth check? (True/False): ",
            "prompt_on_new": False}
    )

    @field_validator("connectors", "tokens", mode="before")
    @classmethod
    def validate_sets(cls, v):
        if isinstance(v, str):
            return set(v.split(","))
        return v


class FundingRateArbitrage(StrategyV2Base):
    quote_markets_map = {
        "hyperliquid_perpetual": "USD",
        "binance_perpetual": "USDT",
        "bybit_perpetual": "USDT",
        "okx_perpetual": "USDT",
        "gate_io_perpetual": "USDT",
        "kucoin_perpetual": "USDT",
        "bingx_perpetual": "USDT",
        "bitget_perpetual": "USDT",
        "mexc_perpetual": "USDT",
        "phemex_perpetual": "USDT",
    }
    funding_payment_interval_map = {
        "binance_perpetual": 60 * 60 * 8,  # 8 hours
        "bybit_perpetual": 60 * 60 * 8,    # 8 hours
        "okx_perpetual": 60 * 60 * 8,      # 8 hours
        "gate_io_perpetual": 60 * 60 * 8,  # 8 hours
        "kucoin_perpetual": 60 * 60 * 8,   # 8 hours
        "bingx_perpetual": 60 * 60 * 8,    # 8 hours
        "bitget_perpetual": 60 * 60 * 8,   # 8 hours
        "mexc_perpetual": 60 * 60 * 8,     # 8 hours
        "phemex_perpetual": 60 * 60 * 8,   # 8 hours
        "hyperliquid_perpetual": 60 * 60 * 1,  # 1 hour
    }
    # Exchanges that only support ONEWAY position mode (most support HEDGE)
    oneway_only_exchanges = {
        "hyperliquid_perpetual",
        # Add other ONEWAY-only exchanges here if needed
    }
    funding_profitability_interval = 60 * 60 * 24

    @classmethod
    def get_trading_pair_for_connector(cls, token, connector):
        return f"{token}-{cls.quote_markets_map.get(connector, 'USDT')}"

    @classmethod
    def init_markets(cls, config: FundingRateArbitrageConfig):
        markets = {}
        for connector in config.connectors:
            trading_pairs = {cls.get_trading_pair_for_connector(token, connector) for token in config.tokens}
            markets[connector] = trading_pairs
        cls.markets = markets

    def __init__(self, connectors: Dict[str, ConnectorBase], config: FundingRateArbitrageConfig):
        super().__init__(connectors, config)
        self.config = config
        self.active_funding_arbitrages = {}
        self.pending_funding_arbitrages = {}  # NEW: positions awaiting validation
        self.stopped_funding_arbitrages = {token: [] for token in self.config.tokens}
        self.pending_validation_max_attempts = 3

        # Initialize Telegram alerter for critical event monitoring
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.alerter = TelegramAlerter(bot_token, chat_id)

        # Initialize rate limiter to prevent IP bans
        self.rate_limiter = get_rate_limiter()

        # Track errors for high error rate alerting
        self.error_count = 0
        self.last_error_reset = None

        # BUG FIX #20: Track last statistics logging time
        self.last_stats_log_time = None
        self.stats_log_interval = 300  # Log stats every 5 minutes

    def start(self, clock: Clock, timestamp: float) -> None:
        """
        Start the strategy.
        :param clock: Clock to use.
        :param timestamp: Current time.
        """
        self._last_timestamp = timestamp

        # BUG FIX #20: Add comprehensive startup logging
        self.logger().info("=" * 80)
        self.logger().info("🚀 FUNDING RATE ARBITRAGE BOT STARTING")
        self.logger().info("=" * 80)
        self.logger().info(f"📅 Timestamp: {timestamp}")
        self.logger().info(f"📊 Configuration:")
        self.logger().info(f"   • Connectors: {', '.join(sorted(self.config.connectors))}")
        self.logger().info(f"   • Tokens: {', '.join(sorted(self.config.tokens))}")
        self.logger().info(f"   • Leverage: {self.config.leverage}x")
        self.logger().info(f"   • Min funding rate: {self.config.min_funding_rate_profitability:.4%}")
        self.logger().info(f"   • Position size: ${self.config.position_size_quote}")
        self.logger().info(f"   • Max slippage: {self.config.max_slippage_pct:.2%}")
        self.logger().info(f"   • Min time to funding: {self.config.min_time_to_next_funding_seconds}s")
        self.logger().info(f"   • Order book depth check: {self.config.check_order_book_depth_enabled}")
        if self.config.check_order_book_depth_enabled:
            self.logger().info(f"   • Min order book depth: {self.config.min_order_book_depth_multiplier}x position size")
        self.logger().info(f"   • Position validation: {self.config.position_validation_enabled}")
        self.logger().info(f"   • Emergency close on imbalance: {self.config.emergency_close_on_imbalance}")
        self.logger().info(f"   • Max position imbalance: {self.config.max_position_imbalance_pct:.1%}")
        self.logger().info("=" * 80)

        self.apply_initial_setting()
        self.check_quote_currency_consistency()

        self.logger().info("✅ Strategy initialization complete")
        self.logger().info("=" * 80)

    def check_quote_currency_consistency(self):
        """
        WARNING: Check if exchanges use different quote currencies (USDT vs USD).
        This is important because USDT can depeg from USD, causing false arbitrage signals.
        """
        quote_currencies = set()
        for connector_name in self.config.connectors:
            quote = self.quote_markets_map.get(connector_name, "USDT")
            quote_currencies.add(quote)

        if len(quote_currencies) > 1:
            self.logger().warning("⚠️  CRITICAL WARNING: Multiple quote currencies detected!")
            self.logger().warning(f"   Quote currencies in use: {quote_currencies}")
            self.logger().warning("   Risk: USDT can depeg from USD, causing false arbitrage signals!")
            self.logger().warning("   Example: USDT at $0.95 makes BTC-USDT appear cheaper than BTC-USD")
            self.logger().warning("   Recommendation:")
            self.logger().warning("     1. Monitor USDT/USD price manually")
            self.logger().warning("     2. Stop bot if USDT depeg > 0.5%")
            self.logger().warning("     3. OR: Use only exchanges with same quote currency")

            # Send Telegram alert
            self.alerter.warning(
                title="Multiple Quote Currencies",
                message=f"Bot uses multiple quote currencies: {quote_currencies}",
                details={
                    "Quote Currencies": ", ".join(quote_currencies),
                    "Risk": "USDT depeg can cause false arbitrage",
                    "Action": "Monitor USDT/USD price manually",
                    "Stop Threshold": "USDT depeg > 0.5%"
                }
            )
        else:
            self.logger().info(f"✅ Quote currency check: All exchanges use {list(quote_currencies)[0]}")

    def apply_initial_setting(self):
        """
        BUG FIX #19: Apply initial settings (position mode, leverage) with error handling.
        Prevents bot crash if exchange doesn't support requested mode or leverage.
        """
        for connector_name, connector in self.connectors.items():
            if self.is_perpetual(connector_name):
                try:
                    # Check if exchange only supports ONEWAY mode, otherwise use HEDGE for better risk management
                    position_mode = PositionMode.ONEWAY if connector_name in self.oneway_only_exchanges else PositionMode.HEDGE

                    # Set position mode with error handling
                    try:
                        connector.set_position_mode(position_mode)
                        self.logger().info(f"✅ Set {connector_name} position mode to {position_mode}")
                    except Exception as e:
                        self.logger().error(f"❌ Failed to set position mode for {connector_name}: {e}")
                        self.alerter.warning(
                            title="Position Mode Setup Failed",
                            message=f"Could not set {position_mode} mode on {connector_name}",
                            details={
                                "Exchange": connector_name,
                                "Attempted Mode": str(position_mode),
                                "Error": str(e),
                                "Action": "Check exchange API documentation for supported position modes"
                            }
                        )
                        # Continue with other connectors even if this fails
                        continue

                    # Set leverage for each trading pair
                    trading_pairs = self.market_data_provider.get_trading_pairs(connector_name)
                    for trading_pair in trading_pairs:
                        try:
                            connector.set_leverage(trading_pair, self.config.leverage)
                            self.logger().debug(f"✅ Set {connector_name} {trading_pair} leverage to {self.config.leverage}x")
                        except Exception as e:
                            self.logger().error(f"❌ Failed to set leverage for {connector_name} {trading_pair}: {e}")
                            self.alerter.warning(
                                title="Leverage Setup Failed",
                                message=f"Could not set {self.config.leverage}x leverage on {connector_name}",
                                details={
                                    "Exchange": connector_name,
                                    "Trading Pair": trading_pair,
                                    "Attempted Leverage": f"{self.config.leverage}x",
                                    "Error": str(e),
                                    "Action": "Check if leverage exceeds exchange maximum or if API key has sufficient permissions"
                                }
                            )
                            # Continue with next trading pair

                except Exception as e:
                    self.logger().error(f"❌ Unexpected error applying initial settings for {connector_name}: {e}")
                    self.alerter.warning(
                        title="Exchange Setup Error",
                        message=f"Failed to configure {connector_name}",
                        details={
                            "Exchange": connector_name,
                            "Error": str(e),
                            "Action": "Check exchange connection and API key permissions"
                        }
                    )
                    self.track_error()
                    # Continue with other connectors

    def get_connectors_in_use(self) -> Set[str]:
        connectors = set()
        # Include active positions
        for info in self.active_funding_arbitrages.values():
            connectors.add(info["connector_1"])
            connectors.add(info["connector_2"])
        # Also include pending positions (don't allow new positions on same connectors)
        for info in self.pending_funding_arbitrages.values():
            connectors.add(info["connector_1"])
            connectors.add(info["connector_2"])
        return connectors

    # ========================================
    # SAFE API WRAPPERS (Bug fixes #1-10)
    # With rate limiting to prevent IP bans
    # ========================================

    def safe_get_price(self, connector_name: str, trading_pair: str, price_type=PriceType.MidPrice) -> Decimal | None:
        """
        Safe wrapper for get_price_by_type with error handling.
        Returns None if price unavailable instead of crashing.
        """
        # Apply rate limiting
        self.rate_limiter.wait_if_needed(connector_name)

        try:
            price = self.market_data_provider.get_price_by_type(
                connector_name=connector_name,
                trading_pair=trading_pair,
                price_type=price_type
            )
            if price is None:
                self.logger().warning(f"Price is None for {connector_name} {trading_pair}")
                return None
            return Decimal(str(price))
        except (TypeError, ValueError, AttributeError) as e:
            self.logger().error(f"Error getting price for {connector_name} {trading_pair}: {e}")
            self.track_error()
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting price for {connector_name} {trading_pair}: {e}")
            self.track_error()
            return None

    def safe_get_price_for_volume(self, connector_name: str, trading_pair: str, quote_volume: Decimal, is_buy: bool) -> Decimal | None:
        """Safe wrapper for get_price_for_quote_volume with error handling."""
        # Apply rate limiting
        self.rate_limiter.wait_if_needed(connector_name)

        try:
            result = self.market_data_provider.get_price_for_quote_volume(
                connector_name=connector_name,
                trading_pair=trading_pair,
                quote_volume=quote_volume,
                is_buy=is_buy
            )
            if result is None or result.result_price is None:
                self.logger().warning(f"Price for volume is None for {connector_name} {trading_pair}")
                return None
            return Decimal(str(result.result_price))
        except (TypeError, ValueError, AttributeError) as e:
            self.logger().error(f"Error getting price for volume {connector_name} {trading_pair}: {e}")
            self.track_error()
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting price for volume {connector_name} {trading_pair}: {e}")
            self.track_error()
            return None

    def safe_get_balance(self, connector_name: str, currency: str) -> Decimal | None:
        """Safe wrapper for get_available_balance with error handling."""
        # Apply rate limiting
        self.rate_limiter.wait_if_needed(connector_name)

        try:
            connector = self.connectors.get(connector_name)
            if connector is None:
                self.logger().error(f"Connector {connector_name} not available")
                return None
            balance = connector.get_available_balance(currency)
            if balance is None:
                self.logger().warning(f"Balance is None for {connector_name} {currency}")
                return Decimal("0")
            return Decimal(str(balance))
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            self.logger().error(f"Error getting balance for {connector_name} {currency}: {e}")
            self.track_error()
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting balance for {connector_name} {currency}: {e}")
            self.track_error()
            return None

    def safe_get_fee(self, connector_name: str, base_currency: str, quote_currency: str,
                    order_type: OrderType, order_side: TradeType, amount: Decimal,
                    price: Decimal, is_maker: bool, position_action: PositionAction) -> Decimal | None:
        """Safe wrapper for get_fee with error handling."""
        # Apply rate limiting
        self.rate_limiter.wait_if_needed(connector_name)

        try:
            connector = self.connectors.get(connector_name)
            if connector is None:
                self.logger().error(f"Connector {connector_name} not available")
                return None
            fee_obj = connector.get_fee(
                base_currency=base_currency,
                quote_currency=quote_currency,
                order_type=order_type,
                order_side=order_side,
                amount=amount,
                price=price,
                is_maker=is_maker,
                position_action=position_action
            )
            if fee_obj is None or fee_obj.percent is None:
                self.logger().warning(f"Fee is None for {connector_name}")
                # Return conservative estimate: 0.1% (typical taker fee)
                return Decimal("0.001")
            return Decimal(str(fee_obj.percent))
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            self.logger().error(f"Error getting fee for {connector_name}: {e}")
            self.track_error()
            return Decimal("0.001")  # Fallback to conservative estimate
        except Exception as e:
            self.logger().error(f"Unexpected error getting fee for {connector_name}: {e}")
            self.track_error()
            return Decimal("0.001")

    def safe_split_trading_pair(self, trading_pair: str) -> tuple[str, str] | None:
        """
        Safely split trading pair into base and quote currencies.
        Handles multiple formats: BTC-USDT, BTC/USDT, BTCUSDT.
        """
        try:
            # Try different separators
            for sep in ["-", "/", "_"]:
                if sep in trading_pair:
                    parts = trading_pair.split(sep)
                    if len(parts) == 2:
                        return parts[0], parts[1]

            # If no separator found, log warning
            self.logger().error(f"Cannot split trading_pair: {trading_pair} (no separator found)")
            return None
        except Exception as e:
            self.logger().error(f"Error splitting trading_pair {trading_pair}: {e}")
            return None

    def track_error(self):
        """
        Track errors and send alert if error rate is too high.
        Resets error count every hour.
        """
        import time

        current_time = time.time()

        # Reset error count every hour
        if self.last_error_reset is None:
            self.last_error_reset = current_time
        elif current_time - self.last_error_reset > 3600:  # 1 hour
            if self.error_count > 0:
                self.logger().info(f"Resetting error count: {self.error_count} errors in last hour")
            self.error_count = 0
            self.last_error_reset = current_time

        # Increment error count
        self.error_count += 1

        # Alert if error rate exceeds threshold (20 errors per hour)
        if self.error_count >= 20:
            self.alerter.alert_high_error_rate(
                error_count=self.error_count,
                time_period="1 hour"
            )

    def validate_sufficient_balance(self, connector_1: str, connector_2: str, position_size_quote: Decimal) -> tuple[bool, str]:
        """
        Validate that both connectors have sufficient balance for the position.
        Returns (is_valid, error_message)
        """
        # BUG FIX #12: Check leverage before division
        if self.config.leverage <= 0:
            return False, f"Invalid leverage: {self.config.leverage}"

        quote_1 = self.quote_markets_map.get(connector_1, "USDT")
        quote_2 = self.quote_markets_map.get(connector_2, "USDT")

        # BUG FIX #3: Use safe_get_balance instead of direct call
        balance_1 = self.safe_get_balance(connector_1, quote_1)
        balance_2 = self.safe_get_balance(connector_2, quote_2)

        if balance_1 is None:
            return False, f"{connector_1} balance unavailable"
        if balance_2 is None:
            return False, f"{connector_2} balance unavailable"

        # Required margin = position_size / leverage
        required_margin = position_size_quote / self.config.leverage

        # Add 10% buffer for fees and safety
        required_margin_with_buffer = required_margin * Decimal("1.10")

        if balance_1 < required_margin_with_buffer:
            return False, f"{connector_1} insufficient balance: {balance_1} < {required_margin_with_buffer} required"

        if balance_2 < required_margin_with_buffer:
            return False, f"{connector_2} insufficient balance: {balance_2} < {required_margin_with_buffer} required"

        return True, ""

    def check_slippage(self, token: str, connector_1: str, connector_2: str,
                      expected_price_1: Decimal, expected_price_2: Decimal,
                      quote_volume: Decimal) -> tuple[bool, str]:
        """
        Check if current market prices are within acceptable slippage range.
        Returns (is_acceptable, warning_message)
        """
        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        # BUG FIX #1: Use safe_get_price instead of direct call
        current_price_1 = self.safe_get_price(connector_1, trading_pair_1, PriceType.MidPrice)
        current_price_2 = self.safe_get_price(connector_2, trading_pair_2, PriceType.MidPrice)

        if current_price_1 is None:
            return False, f"Price unavailable for {connector_1} {trading_pair_1}"
        if current_price_2 is None:
            return False, f"Price unavailable for {connector_2} {trading_pair_2}"

        # Protect against zero prices
        if expected_price_1 <= 0 or expected_price_2 <= 0:
            return False, f"Invalid expected prices: {expected_price_1}, {expected_price_2}"

        # Calculate slippage
        slippage_1 = abs(current_price_1 - expected_price_1) / expected_price_1
        slippage_2 = abs(current_price_2 - expected_price_2) / expected_price_2

        max_slippage = max(slippage_1, slippage_2)

        if max_slippage > self.config.max_slippage_pct:
            return False, f"Slippage too high: {max_slippage:.4%} > {self.config.max_slippage_pct:.4%} (C1: {slippage_1:.4%}, C2: {slippage_2:.4%})"

        if max_slippage > self.config.max_slippage_pct * Decimal("0.5"):
            return True, f"Warning: Slippage {max_slippage:.4%} (C1: {slippage_1:.4%}, C2: {slippage_2:.4%})"

        return True, ""

    def check_time_to_funding(self, funding_info_report: Dict, connector_1: str, connector_2: str) -> tuple[bool, str]:
        """
        BUG FIX #17: Check if there's enough time before next funding settlement.
        This prevents opening positions too close to funding time, which would miss the payment.

        Returns (is_safe, message)
        """
        if connector_1 not in funding_info_report or connector_2 not in funding_info_report:
            return False, f"Funding info not available for {connector_1} or {connector_2}"

        funding_info_1 = funding_info_report[connector_1]
        funding_info_2 = funding_info_report[connector_2]

        # Check connector 1
        if funding_info_1.next_funding_utc_timestamp is not None and self.current_timestamp is not None:
            time_to_funding_1 = funding_info_1.next_funding_utc_timestamp - self.current_timestamp
            if time_to_funding_1 < self.config.min_time_to_next_funding_seconds:
                return False, f"Too close to funding on {connector_1}: {time_to_funding_1:.0f}s < {self.config.min_time_to_next_funding_seconds}s"

        # Check connector 2
        if funding_info_2.next_funding_utc_timestamp is not None and self.current_timestamp is not None:
            time_to_funding_2 = funding_info_2.next_funding_utc_timestamp - self.current_timestamp
            if time_to_funding_2 < self.config.min_time_to_next_funding_seconds:
                return False, f"Too close to funding on {connector_2}: {time_to_funding_2:.0f}s < {self.config.min_time_to_next_funding_seconds}s"

        return True, ""

    def check_order_book_depth(self, token: str, connector_1: str, connector_2: str,
                               position_size_quote: Decimal, trade_side: TradeType) -> tuple[bool, str]:
        """
        BUG FIX #18: Check if order book has sufficient depth for both connectors.
        This prevents entering on illiquid markets with high slippage risk.

        Returns (is_sufficient, message)
        """
        if not self.config.check_order_book_depth_enabled:
            return True, "Order book depth check disabled"

        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        # Check connector 1 (buying if trade_side is BUY)
        depth_ok_1, depth_msg_1 = self._check_single_order_book_depth(
            connector_1, trading_pair_1, position_size_quote, is_buy=(trade_side == TradeType.BUY)
        )
        if not depth_ok_1:
            return False, f"{connector_1}: {depth_msg_1}"

        # Check connector 2 (selling if trade_side is BUY)
        depth_ok_2, depth_msg_2 = self._check_single_order_book_depth(
            connector_2, trading_pair_2, position_size_quote, is_buy=(trade_side != TradeType.BUY)
        )
        if not depth_ok_2:
            return False, f"{connector_2}: {depth_msg_2}"

        return True, f"Order book depth OK (C1: {depth_msg_1}, C2: {depth_msg_2})"

    def _check_single_order_book_depth(self, connector_name: str, trading_pair: str,
                                       quote_volume: Decimal, is_buy: bool) -> tuple[bool, str]:
        """
        Check order book depth for a single connector/pair.

        Returns (is_sufficient, message)
        """
        # Apply rate limiting
        self.rate_limiter.wait_if_needed(connector_name)

        try:
            connector = self.connectors.get(connector_name)
            if connector is None:
                return False, f"Connector {connector_name} not available"

            order_book = connector.get_order_book(trading_pair)
            if order_book is None:
                return False, "Order book not available"

            # Get price for volume calculation
            price = self.safe_get_price(connector_name, trading_pair, PriceType.MidPrice)
            if price is None or price <= 0:
                return False, "Price not available for depth check"

            # Calculate required base amount
            required_base_amount = quote_volume / price

            # Check appropriate side of order book
            if is_buy:
                # For buying, we need asks (sell orders)
                total_volume = sum(Decimal(str(level.amount)) for level in order_book.ask_entries()[:20])
                side_name = "asks"
            else:
                # For selling, we need bids (buy orders)
                total_volume = sum(Decimal(str(level.amount)) for level in order_book.bid_entries()[:20])
                side_name = "bids"

            # Require minimum depth (e.g., 3x the required amount)
            min_required = required_base_amount * self.config.min_order_book_depth_multiplier

            if total_volume < min_required:
                return False, f"Insufficient {side_name} depth: {total_volume:.4f} < {min_required:.4f}"

            return True, f"{side_name} depth {total_volume:.4f}"

        except (TypeError, ValueError, AttributeError) as e:
            self.logger().error(f"Error checking order book depth for {connector_name} {trading_pair}: {e}")
            self.track_error()
            return False, f"Order book check failed: {e}"
        except Exception as e:
            self.logger().error(f"Unexpected error checking order book depth for {connector_name} {trading_pair}: {e}")
            self.track_error()
            return False, f"Order book check failed: {e}"

    def validate_position_hedge(self, token: str) -> tuple[bool, str]:
        """
        Validate that positions are properly hedged (equal notional values).
        Returns (is_hedged, message)
        """
        if token not in self.active_funding_arbitrages:
            return True, "No active position"

        arbitrage_info = self.active_funding_arbitrages[token]
        connector_1 = arbitrage_info["connector_1"]
        connector_2 = arbitrage_info["connector_2"]

        # Get executors
        executors = self.filter_executors(
            executors=self.get_all_executors(),
            filter_func=lambda x: x.id in arbitrage_info["executors_ids"]
        )

        if len(executors) != 2:
            return False, f"Expected 2 executors, found {len(executors)}"

        # Find which executor belongs to which connector
        executor_1 = None
        executor_2 = None
        for executor in executors:
            if executor.connector_name == connector_1:
                executor_1 = executor
            elif executor.connector_name == connector_2:
                executor_2 = executor

        if executor_1 is None or executor_2 is None:
            return False, f"Could not find executors for both connectors"

        # BUG FIX #7: Check if filled_amount is None before comparison
        if executor_1.filled_amount is None or executor_1.filled_amount <= 0:
            return False, f"{connector_1} position not filled: {executor_1.filled_amount}"

        if executor_2.filled_amount is None or executor_2.filled_amount <= 0:
            return False, f"{connector_2} position not filled: {executor_2.filled_amount}"

        # Get current prices
        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        # BUG FIX #1: Use safe_get_price instead of direct call
        price_1 = self.safe_get_price(connector_1, trading_pair_1, PriceType.MidPrice)
        price_2 = self.safe_get_price(connector_2, trading_pair_2, PriceType.MidPrice)

        if price_1 is None:
            return False, f"Price unavailable for {connector_1} {trading_pair_1}"
        if price_2 is None:
            return False, f"Price unavailable for {connector_2} {trading_pair_2}"

        # Calculate notional values
        notional_1 = abs(executor_1.filled_amount) * price_1
        notional_2 = abs(executor_2.filled_amount) * price_2

        # Check imbalance
        if notional_1 == 0 or notional_2 == 0:
            return False, f"Zero notional value detected: {notional_1}, {notional_2}"

        imbalance = abs(notional_1 - notional_2) / max(notional_1, notional_2)

        if imbalance > self.config.max_position_imbalance_pct:
            return False, f"Position imbalance {imbalance:.2%} > {self.config.max_position_imbalance_pct:.2%} (N1: ${notional_1:.2f}, N2: ${notional_2:.2f})"

        if imbalance > self.config.max_position_imbalance_pct * Decimal("0.5"):
            return True, f"Warning: Position imbalance {imbalance:.2%} (N1: ${notional_1:.2f}, N2: ${notional_2:.2f})"

        return True, f"Hedge OK: imbalance {imbalance:.2%}"

    def get_position_size_quote(self, connector_1: str, connector_2: str) -> Decimal:
        """
        Calculate the maximum position size in quote currency considering available balance and leverage.
        Note: position_size_quote is the notional value WITHOUT leverage, so we need to ensure
        we have enough margin (notional / leverage) available.
        """
        # BUG FIX #12: Check leverage before calculation
        if self.config.leverage <= 0:
            self.logger().error(f"Invalid leverage: {self.config.leverage}")
            return Decimal("0")

        quote_1 = self.quote_markets_map.get(connector_1, "USDT")
        quote_2 = self.quote_markets_map.get(connector_2, "USDT")

        # BUG FIX #3: Use safe_get_balance instead of direct call
        balance_1 = self.safe_get_balance(connector_1, quote_1)
        balance_2 = self.safe_get_balance(connector_2, quote_2)

        if balance_1 is None or balance_2 is None:
            self.logger().warning(f"Balance unavailable for {connector_1} or {connector_2}")
            return Decimal("0")

        # Calculate maximum position size based on available balance and leverage
        # For perpetuals: required_margin = notional_value / leverage
        # So: max_notional = available_balance * leverage
        # However, we limit to min(config.position_size_quote, available_balance * leverage)
        # to be conservative and leave some buffer for fees
        max_position_1 = balance_1 * self.config.leverage * Decimal("0.95")  # 95% to leave buffer for fees
        max_position_2 = balance_2 * self.config.leverage * Decimal("0.95")

        # Use the configured position size, but don't exceed available balance * leverage
        return min(self.config.position_size_quote, max_position_1, max_position_2)

    def get_funding_info_by_token(self, token, connectors: Set[str] | None = None):
        """
        This method provides the funding rates across all the connectors
        """
        funding_rates = {}
        connectors_to_use = connectors or set(self.connectors.keys())
        for connector_name in connectors_to_use:
            try:
                connector = self.connectors[connector_name]
                trading_pair = self.get_trading_pair_for_connector(token, connector_name)
                funding_info = connector.get_funding_info(trading_pair)
                # Only add if funding_info is not None
                if funding_info is not None:
                    funding_rates[connector_name] = funding_info
            except Exception as e:
                self.logger().warning(f"Error getting funding info for {token} on {connector_name}: {e}")
                continue
        return funding_rates

    def get_current_profitability_after_fees(
            self, token: str, connector_1: str, connector_2: str, side: TradeType, quote_volume: Decimal):
        """
        This methods compares the profitability of buying at market in the two exchanges. If the side is TradeType.BUY
        means that the operation is long on connector 1 and short on connector 2.

        IMPORTANT: This calculates the cost of BOTH opening AND closing positions, as both incur fees.
        """
        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        # BUG FIX #2: Use safe_get_price_for_volume instead of direct call
        connector_1_price = self.safe_get_price_for_volume(
            connector_1, trading_pair_1, quote_volume, is_buy=(side == TradeType.BUY)
        )
        connector_2_price = self.safe_get_price_for_volume(
            connector_2, trading_pair_2, quote_volume, is_buy=(side != TradeType.BUY)
        )

        if connector_1_price is None or connector_2_price is None:
            self.logger().error(f"Price unavailable for profitability calculation: {connector_1} or {connector_2}")
            return Decimal("-999")  # Return very negative value to skip this opportunity

        # BUG FIX #6: Use safe_split_trading_pair instead of direct split
        pair_1_parts = self.safe_split_trading_pair(trading_pair_1)
        pair_2_parts = self.safe_split_trading_pair(trading_pair_2)

        if pair_1_parts is None or pair_2_parts is None:
            self.logger().error(f"Cannot split trading pairs: {trading_pair_1} or {trading_pair_2}")
            return Decimal("-999")

        base_1, quote_1 = pair_1_parts
        base_2, quote_2 = pair_2_parts

        # Protect against zero prices
        if connector_1_price <= 0 or connector_2_price <= 0:
            self.logger().error(f"Invalid prices: {connector_1_price}, {connector_2_price}")
            return Decimal("-999")

        # Calculate fees for OPENING positions
        # BUG FIX #4: Use safe_get_fee instead of direct call
        estimated_fees_open_connector_1 = self.safe_get_fee(
            connector_1, base_1, quote_1,
            OrderType.MARKET, side, quote_volume / connector_1_price,
            connector_1_price, False, PositionAction.OPEN
        )
        estimated_fees_open_connector_2 = self.safe_get_fee(
            connector_2, base_2, quote_2,
            OrderType.MARKET, TradeType.BUY if side != TradeType.BUY else TradeType.SELL,
            quote_volume / connector_2_price, connector_2_price, False, PositionAction.OPEN
        )

        # Calculate fees for CLOSING positions (opposite sides)
        estimated_fees_close_connector_1 = self.safe_get_fee(
            connector_1, base_1, quote_1,
            OrderType.MARKET, TradeType.BUY if side != TradeType.BUY else TradeType.SELL,
            quote_volume / connector_1_price, connector_1_price, False, PositionAction.CLOSE
        )
        estimated_fees_close_connector_2 = self.safe_get_fee(
            connector_2, base_2, quote_2,
            OrderType.MARKET, side,  # BUG FIX #15: Closes the opposite position opened on connector_2
            quote_volume / connector_2_price, connector_2_price, False, PositionAction.CLOSE
        )

        if None in [estimated_fees_open_connector_1, estimated_fees_open_connector_2,
                   estimated_fees_close_connector_1, estimated_fees_close_connector_2]:
            self.logger().error(f"Fee calculation failed for {connector_1} or {connector_2}")
            return Decimal("-999")

        # Total fees = open + close for both connectors
        total_fees = (estimated_fees_open_connector_1 + estimated_fees_close_connector_1 +
                     estimated_fees_open_connector_2 + estimated_fees_close_connector_2)

        if side == TradeType.BUY:
            estimated_trade_pnl_pct = (connector_2_price - connector_1_price) / connector_1_price
        else:
            estimated_trade_pnl_pct = (connector_1_price - connector_2_price) / connector_2_price
        return estimated_trade_pnl_pct - total_fees

    def get_most_profitable_combination(self, funding_info_report: Dict):
        best_combination = None
        highest_profitability = 0
        for connector_1 in funding_info_report:
            for connector_2 in funding_info_report:
                if connector_1 != connector_2:
                    quote_1 = self.quote_markets_map.get(connector_1, "USDT")
                    quote_2 = self.quote_markets_map.get(connector_2, "USDT")
                    if quote_1 != quote_2:
                        self.logger().warning(
                            f"Skipping pair {connector_1}/{connector_2} due to mismatched quotes ({quote_1} vs {quote_2})"
                        )
                        continue
                    rate_connector_1 = self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_1)
                    rate_connector_2 = self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_2)
                    funding_rate_diff = abs(rate_connector_1 - rate_connector_2) * self.funding_profitability_interval
                    if funding_rate_diff > highest_profitability:
                        trade_side = TradeType.BUY if rate_connector_1 < rate_connector_2 else TradeType.SELL
                        highest_profitability = funding_rate_diff
                        best_combination = (connector_1, connector_2, trade_side, funding_rate_diff)
        return best_combination

    def get_normalized_funding_rate_in_seconds(self, funding_info_report, connector_name):
        """
        BUG FIX #13: Safe access to funding_info_report with validation.
        """
        # Check if connector exists in report
        if connector_name not in funding_info_report:
            self.logger().warning(f"Connector {connector_name} not in funding_info_report")
            return Decimal("0")

        funding_info = funding_info_report[connector_name]
        if funding_info is None or funding_info.rate is None:
            self.logger().warning(f"Funding info or rate is None for {connector_name}")
            return Decimal("0")

        interval = self.funding_payment_interval_map.get(connector_name, 60 * 60 * 8)
        if interval <= 0:
            self.logger().error(f"Invalid funding payment interval for {connector_name}: {interval}")
            return Decimal("0")

        return Decimal(str(funding_info.rate)) / Decimal(str(interval))

    def create_actions_proposal(self) -> List[CreateExecutorAction]:
        """
        In this method we are going to evaluate if a new set of positions has to be created for each of the tokens that
        don't have an active arbitrage.
        More filters can be applied to limit the creation of the positions, since the current logic is only checking for
        positive pnl between funding rate. Is logged and computed the trading profitability at the time for entering
        at market to open the possibilities for other people to create variations like sending limit position executors
        and if one gets filled buy market the other one to improve the entry prices.
        """
        create_actions = []
        connectors_in_use = self.get_connectors_in_use()
        available_connectors = set(self.config.connectors) - connectors_in_use
        if len(available_connectors) < 2:
            return create_actions

        for token in self.config.tokens:
            if token not in self.active_funding_arbitrages:
                funding_info_report = self.get_funding_info_by_token(token, available_connectors)
                if not funding_info_report or len(funding_info_report) < 2:
                    continue
                best_combination = self.get_most_profitable_combination(funding_info_report)
                if best_combination is None:
                    continue
                connector_1, connector_2, trade_side, expected_profitability = best_combination
                if expected_profitability >= self.config.min_funding_rate_profitability:
                    position_size_quote = self.get_position_size_quote(connector_1, connector_2)
                    if position_size_quote <= 0:
                        self.logger().warning(f"Skipping {token}: position_size_quote is zero or negative")
                        continue

                    # SAFETY CHECK 1: Validate sufficient balance
                    balance_valid, balance_msg = self.validate_sufficient_balance(connector_1, connector_2, position_size_quote)
                    if not balance_valid:
                        self.logger().warning(f"Skipping {token}: {balance_msg}")
                        continue

                    # SAFETY CHECK 1.5: Check time to next funding settlement (BUG FIX #17)
                    # Don't open position if too close to funding time (would miss payment)
                    funding_time_ok, funding_time_msg = self.check_time_to_funding(funding_info_report, connector_1, connector_2)
                    if not funding_time_ok:
                        self.logger().warning(f"Skipping {token}: {funding_time_msg}")
                        continue

                    current_profitability = self.get_current_profitability_after_fees(
                        token, connector_1, connector_2, trade_side, position_size_quote
                    )

                    # SAFETY CHECK 2: Slippage protection
                    trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
                    trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

                    # BUG FIX #16: Use safe_get_price instead of direct call to prevent TypeError crash
                    expected_price_1 = self.safe_get_price(connector_1, trading_pair_1, PriceType.MidPrice)
                    expected_price_2 = self.safe_get_price(connector_2, trading_pair_2, PriceType.MidPrice)

                    if expected_price_1 is None or expected_price_2 is None:
                        self.logger().warning(f"Skipping {token}: Price unavailable for slippage check (C1: {expected_price_1}, C2: {expected_price_2})")
                        continue

                    slippage_ok, slippage_msg = self.check_slippage(
                        token, connector_1, connector_2, expected_price_1, expected_price_2, position_size_quote
                    )
                    if not slippage_ok:
                        self.logger().warning(f"Skipping {token}: {slippage_msg}")
                        continue
                    elif slippage_msg:
                        self.logger().info(f"{token}: {slippage_msg}")

                    # SAFETY CHECK 3: Order book depth protection (BUG FIX #18)
                    # Ensure sufficient liquidity to execute and close positions
                    depth_ok, depth_msg = self.check_order_book_depth(token, connector_1, connector_2, position_size_quote, trade_side)
                    if not depth_ok:
                        self.logger().warning(f"Skipping {token}: {depth_msg}")
                        continue
                    elif "OK" in depth_msg:
                        self.logger().debug(f"{token}: {depth_msg}")

                    if self.config.trade_profitability_condition_to_enter:
                        if current_profitability < 0:
                            self.logger().info(f"Best Combination: {connector_1} | {connector_2} | {trade_side}"
                                               f"Funding rate profitability: {expected_profitability}"
                                               f"Trading profitability after fees: {current_profitability}"
                                               f"Trade profitability is negative, skipping...")
                            continue
                    self.logger().info(f"Best Combination: {connector_1} | {connector_2} | {trade_side}"
                                       f"Funding rate profitability: {expected_profitability}"
                                       f"Trading profitability after fees: {current_profitability}"
                                       f"Starting executors...")
                    position_executor_config_1, position_executor_config_2 = self.get_position_executors_config(
                        token, connector_1, connector_2, trade_side, position_size_quote)

                    # Check if configs were created successfully
                    if position_executor_config_1 is None or position_executor_config_2 is None:
                        self.logger().error(f"Failed to create executor configs for {token}, skipping")
                        continue

                    # CRITICAL FIX: Add to PENDING first (not active!)
                    # Position will be validated and moved to active in stop_actions_proposal
                    self.pending_funding_arbitrages[token] = {
                        "connector_1": connector_1,
                        "connector_2": connector_2,
                        "executors_ids": [position_executor_config_1.id, position_executor_config_2.id],
                        "side": trade_side,
                        "funding_payments": [],
                        "position_size_quote": position_size_quote,
                        "timestamp": self.current_timestamp,  # Track when pending started
                        "validation_attempts": 0,
                        "last_validation_error": None,
                    }

                    self.logger().info(f"Position for {token} marked as PENDING. Awaiting validation after execution.")

                    # Add to create_actions list and continue checking other tokens
                    create_actions.extend([CreateExecutorAction(executor_config=position_executor_config_1),
                                          CreateExecutorAction(executor_config=position_executor_config_2)])
                    # Update connectors_in_use and available_connectors for next iteration
                    connectors_in_use.add(connector_1)
                    connectors_in_use.add(connector_2)
                    available_connectors = set(self.config.connectors) - connectors_in_use
                    if len(available_connectors) < 2:
                        break  # No more available connector pairs
        return create_actions

    def validate_pending_positions(self) -> List[StopExecutorAction]:
        """
        CRITICAL: Validate pending positions before marking them as active.
        This prevents race condition where position is marked active before orders execute.

        Returns: List of StopExecutorAction for failed pending positions
        """
        stop_executor_actions = []
        pending_to_remove = []

        for token, pending_info in list(self.pending_funding_arbitrages.items()):
            connector_1 = pending_info["connector_1"]
            connector_2 = pending_info["connector_2"]

            # Check timeout (if pending > 10 seconds, something is wrong)
            time_pending = self.current_timestamp - pending_info.get("timestamp", self.current_timestamp)
            if time_pending > 10:
                self.logger().error(f"Pending position for {token} timed out ({time_pending:.1f}s). Emergency closing.")
                self.alerter.alert_emergency_close(
                    token=token,
                    reason=f"Pending position timeout ({time_pending:.1f}s > 10s)",
                    details={
                        "Exchange 1": connector_1,
                        "Exchange 2": connector_2,
                        "Time Pending": f"{time_pending:.1f}s"
                    }
                )
                # Get executors and close them
                executors = self.filter_executors(
                    executors=self.get_all_executors(),
                    filter_func=lambda x: x.id in pending_info["executors_ids"]
                )
                stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                pending_to_remove.append(token)
                continue

            # Validate position hedge
            is_hedged, hedge_msg = self.validate_position_hedge_for_pending(token, pending_info)

            if is_hedged:
                # SUCCESS: Move to active
                self.active_funding_arbitrages[token] = pending_info
                pending_to_remove.append(token)

                # BUG FIX #20: Enhanced logging for successful position opening
                self.logger().info("=" * 60)
                self.logger().info(f"✅ POSITION OPENED SUCCESSFULLY: {token}")
                self.logger().info("=" * 60)
                self.logger().info(f"📊 Position Details:")
                self.logger().info(f"   • Token: {token}")
                self.logger().info(f"   • Exchange 1: {connector_1}")
                self.logger().info(f"   • Exchange 2: {connector_2}")
                self.logger().info(f"   • Side: {pending_info['side']}")
                self.logger().info(f"   • Position Size: ${pending_info['position_size_quote']}")
                self.logger().info(f"   • Validation: {hedge_msg}")
                self.logger().info(f"   • Time to validate: {self.current_timestamp - pending_info.get('timestamp', self.current_timestamp):.2f}s")
                self.logger().info(f"📈 Active Positions: {len(self.active_funding_arbitrages)} | Pending: {len(self.pending_funding_arbitrages) - 1}")
                self.logger().info("=" * 60)

                # Send success alert
                self.alerter.alert_position_opened(
                    token=token,
                    connector_1=connector_1,
                    connector_2=connector_2,
                    position_size=float(pending_info["position_size_quote"])
                )
            else:
                pending_info["validation_attempts"] = pending_info.get("validation_attempts", 0) + 1
                pending_info["last_validation_error"] = hedge_msg

                # Allow fills/partial fills to complete before failing hard
                recoverable_errors = [
                    "not filled yet",
                    "Zero notional value detected",
                ]
                if any(err.lower() in hedge_msg.lower() for err in recoverable_errors):
                    self.logger().info(
                        f"Pending {token}: waiting for fills ({hedge_msg}). "
                        f"Attempt {pending_info['validation_attempts']}/{self.pending_validation_max_attempts}"
                    )
                    continue

                if pending_info["validation_attempts"] < self.pending_validation_max_attempts:
                    self.logger().warning(
                        f"Pending {token}: validation failed ({hedge_msg}). "
                        f"Retry {pending_info['validation_attempts']}/{self.pending_validation_max_attempts}"
                    )
                    continue

                # FAILURE after retries: Emergency close
                self.logger().error(f"Position validation FAILED for {token}: {hedge_msg}")
                self.alerter.alert_emergency_close(
                    token=token,
                    reason=f"Position validation failed: {hedge_msg}",
                    details={
                        "Exchange 1": connector_1,
                        "Exchange 2": connector_2,
                        "Position Size": f"${pending_info['position_size_quote']}",
                        "Timestamp": str(self.current_timestamp),
                        "Attempts": pending_info["validation_attempts"],
                    }
                )
                # Get executors and close them
                executors = self.filter_executors(
                    executors=self.get_all_executors(),
                    filter_func=lambda x: x.id in pending_info["executors_ids"]
                )
                stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                pending_to_remove.append(token)
                self.stopped_funding_arbitrages[token].append({
                    **pending_info,
                    "close_reason": f"Validation failed after retries: {hedge_msg}"
                })

        # Remove processed pending positions
        for token in pending_to_remove:
            del self.pending_funding_arbitrages[token]

        return stop_executor_actions

    def validate_position_hedge_for_pending(self, token: str, pending_info: dict) -> tuple[bool, str]:
        """
        Validate position hedge for pending position.
        Similar to validate_position_hedge but works with pending_info dict.
        """
        connector_1 = pending_info["connector_1"]
        connector_2 = pending_info["connector_2"]

        # Get executors
        executors = self.filter_executors(
            executors=self.get_all_executors(),
            filter_func=lambda x: x.id in pending_info["executors_ids"]
        )

        if len(executors) != 2:
            return False, f"Expected 2 executors, found {len(executors)}"

        # Find which executor belongs to which connector
        executor_1 = None
        executor_2 = None
        for executor in executors:
            if executor.connector_name == connector_1:
                executor_1 = executor
            elif executor.connector_name == connector_2:
                executor_2 = executor

        if executor_1 is None or executor_2 is None:
            return False, f"Could not find executors for both connectors"

        # Check if filled_amount exists and > 0
        if executor_1.filled_amount is None or executor_1.filled_amount <= 0:
            return False, f"{connector_1} position not filled yet: {executor_1.filled_amount}"

        if executor_2.filled_amount is None or executor_2.filled_amount <= 0:
            return False, f"{connector_2} position not filled yet: {executor_2.filled_amount}"

        # Get current prices
        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        price_1 = self.safe_get_price(connector_1, trading_pair_1, PriceType.MidPrice)
        price_2 = self.safe_get_price(connector_2, trading_pair_2, PriceType.MidPrice)

        if price_1 is None:
            return False, f"Price unavailable for {connector_1} {trading_pair_1}"
        if price_2 is None:
            return False, f"Price unavailable for {connector_2} {trading_pair_2}"

        # Calculate notional values
        notional_1 = abs(executor_1.filled_amount) * price_1
        notional_2 = abs(executor_2.filled_amount) * price_2

        # Check imbalance
        if notional_1 == 0 or notional_2 == 0:
            return False, f"Zero notional value detected: {notional_1}, {notional_2}"

        imbalance = abs(notional_1 - notional_2) / max(notional_1, notional_2)

        if imbalance > self.config.max_position_imbalance_pct:
            return False, f"Position imbalance {imbalance:.2%} > {self.config.max_position_imbalance_pct:.2%} (N1: ${notional_1:.2f}, N2: ${notional_2:.2f})"

        return True, f"Hedge OK: imbalance {imbalance:.2%} (N1: ${notional_1:.2f}, N2: ${notional_2:.2f})"

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        """
        Once the funding rate arbitrage is created we are going to control the funding payments pnl and the current
        pnl of each of the executors at the cost of closing the open position at market.
        If that PNL is greater than the profitability_to_take_profit

        SAFETY: Also monitors position hedge and triggers emergency close if imbalanced.
        """
        stop_executor_actions = []

        # BUG FIX #20: Log periodic statistics
        self.log_periodic_statistics()

        # CRITICAL: First validate pending positions
        pending_stop_actions = self.validate_pending_positions()
        stop_executor_actions.extend(pending_stop_actions)

        tokens_to_remove = []
        for token, funding_arbitrage_info in self.active_funding_arbitrages.items():
            # SAFETY CHECK: Validate position hedge (continuous monitoring)
            if self.config.position_validation_enabled:
                is_hedged, hedge_msg = self.validate_position_hedge(token)
                if not is_hedged:
                    if self.config.emergency_close_on_imbalance:
                        self.logger().error(f"EMERGENCY CLOSE for {token}: {hedge_msg}")

                        # Send critical alert via Telegram
                        self.alerter.alert_emergency_close(
                            token=token,
                            reason=hedge_msg,
                            details={
                                "Exchange 1": funding_arbitrage_info["connector_1"],
                                "Exchange 2": funding_arbitrage_info["connector_2"],
                                "Position Size": f"${self.config.position_size_quote}",
                                "Timestamp": str(self.current_timestamp)
                            }
                        )

                        executors = self.filter_executors(
                            executors=self.get_all_executors(),
                            filter_func=lambda x: x.id in funding_arbitrage_info["executors_ids"]
                        )
                        self.stopped_funding_arbitrages[token].append({
                            **funding_arbitrage_info,
                            "close_reason": f"EMERGENCY: {hedge_msg}"
                        })
                        if len(self.stopped_funding_arbitrages[token]) > 10:
                            self.stopped_funding_arbitrages[token] = self.stopped_funding_arbitrages[token][-10:]
                        stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                        tokens_to_remove.append(token)
                        continue
                    else:
                        self.logger().warning(f"Position hedge warning for {token}: {hedge_msg}")
                elif "Warning" in hedge_msg:
                    self.logger().warning(f"{token}: {hedge_msg}")
                else:
                    self.logger().debug(f"{token}: {hedge_msg}")
            executors = self.filter_executors(
                executors=self.get_all_executors(),
                filter_func=lambda x: x.id in funding_arbitrage_info["executors_ids"]
            )

            # BUG FIX #9: Check if funding_payment.amount is None
            funding_payments_pnl = sum(
                funding_payment.amount if funding_payment.amount is not None else Decimal("0")
                for funding_payment in funding_arbitrage_info["funding_payments"]
            )

            # BUG FIX #8: Check if executor.net_pnl_quote is None
            executors_pnl = sum(
                executor.net_pnl_quote if executor.net_pnl_quote is not None else Decimal("0")
                for executor in executors
            )

            # BUG FIX #11: Don't use default 0 for position_size_quote - it's dangerous!
            position_size = funding_arbitrage_info.get("position_size_quote")
            if position_size is None or position_size <= 0:
                self.logger().error(f"Invalid position_size_quote for {token}: {position_size}")
                continue

            take_profit_condition = executors_pnl + funding_payments_pnl > (
                self.config.profitability_to_take_profit * position_size)

            # Get funding info and check if connectors are available
            funding_info_report = self.get_funding_info_by_token(token)
            connector_1 = funding_arbitrage_info["connector_1"]
            connector_2 = funding_arbitrage_info["connector_2"]

            # Check if both connectors are available in funding_info_report
            if connector_1 not in funding_info_report or connector_2 not in funding_info_report:
                self.logger().warning(f"Connectors {connector_1} or {connector_2} not available for token {token}, skipping stop check")
                continue

            if funding_arbitrage_info["side"] == TradeType.BUY:
                funding_rate_diff = self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_2) - self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_1)
            else:
                funding_rate_diff = self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_1) - self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_2)
            current_funding_condition = funding_rate_diff * self.funding_profitability_interval < self.config.funding_rate_diff_stop_loss

            if take_profit_condition:
                # BUG FIX #20: Enhanced logging for position closing
                total_pnl = float(executors_pnl + funding_payments_pnl)
                total_pnl_pct = (total_pnl / float(position_size)) * 100 if position_size > 0 else 0

                self.logger().info("=" * 60)
                self.logger().info(f"💰 TAKE PROFIT REACHED: {token}")
                self.logger().info("=" * 60)
                self.logger().info(f"📊 Position Details:")
                self.logger().info(f"   • Token: {token}")
                self.logger().info(f"   • Exchange 1: {connector_1}")
                self.logger().info(f"   • Exchange 2: {connector_2}")
                self.logger().info(f"   • Side: {funding_arbitrage_info['side']}")
                self.logger().info(f"   • Position Size: ${position_size}")
                self.logger().info(f"💵 PnL Summary:")
                self.logger().info(f"   • Trading PnL: ${executors_pnl:.2f}")
                self.logger().info(f"   • Funding Payments: ${funding_payments_pnl:.2f}")
                self.logger().info(f"   • Total PnL: ${total_pnl:.2f} ({total_pnl_pct:+.2f}%)")
                self.logger().info(f"   • Funding Payments Collected: {len(funding_arbitrage_info['funding_payments'])}")
                self.logger().info(f"📈 Active Positions: {len(self.active_funding_arbitrages) - 1}")
                self.logger().info("=" * 60)

                # Send alert for position closed with profit
                self.alerter.alert_position_closed(
                    token=token,
                    pnl=total_pnl,
                    reason="Take profit target reached"
                )

                self.stopped_funding_arbitrages[token].append(funding_arbitrage_info)
                # Prevent memory leak: keep only last 10 stopped arbitrages per token
                if len(self.stopped_funding_arbitrages[token]) > 10:
                    self.stopped_funding_arbitrages[token] = self.stopped_funding_arbitrages[token][-10:]
                stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                tokens_to_remove.append(token)
            elif current_funding_condition:
                # BUG FIX #20: Enhanced logging for stop loss
                total_pnl = float(executors_pnl + funding_payments_pnl)
                total_pnl_pct = (total_pnl / float(position_size)) * 100 if position_size > 0 else 0

                self.logger().info("=" * 60)
                self.logger().info(f"🛑 STOP LOSS TRIGGERED: {token}")
                self.logger().info("=" * 60)
                self.logger().info(f"📊 Position Details:")
                self.logger().info(f"   • Token: {token}")
                self.logger().info(f"   • Exchange 1: {connector_1}")
                self.logger().info(f"   • Exchange 2: {connector_2}")
                self.logger().info(f"   • Side: {funding_arbitrage_info['side']}")
                self.logger().info(f"   • Position Size: ${position_size}")
                self.logger().info(f"📉 Reason:")
                self.logger().info(f"   • Funding Rate Diff: {funding_rate_diff:.6f}")
                self.logger().info(f"   • Stop Loss Threshold: {self.config.funding_rate_diff_stop_loss:.6f}")
                self.logger().info(f"💵 PnL Summary:")
                self.logger().info(f"   • Trading PnL: ${executors_pnl:.2f}")
                self.logger().info(f"   • Funding Payments: ${funding_payments_pnl:.2f}")
                self.logger().info(f"   • Total PnL: ${total_pnl:.2f} ({total_pnl_pct:+.2f}%)")
                self.logger().info(f"   • Funding Payments Collected: {len(funding_arbitrage_info['funding_payments'])}")
                self.logger().info(f"📈 Active Positions: {len(self.active_funding_arbitrages) - 1}")
                self.logger().info("=" * 60)

                # Send alert for position closed with stop loss
                self.alerter.alert_position_closed(
                    token=token,
                    pnl=total_pnl,
                    reason="Funding rate stop loss triggered"
                )

                self.stopped_funding_arbitrages[token].append(funding_arbitrage_info)
                # Prevent memory leak: keep only last 10 stopped arbitrages per token
                if len(self.stopped_funding_arbitrages[token]) > 10:
                    self.stopped_funding_arbitrages[token] = self.stopped_funding_arbitrages[token][-10:]
                stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                tokens_to_remove.append(token)

        # Remove stopped arbitrages from active dict
        for token in tokens_to_remove:
            del self.active_funding_arbitrages[token]

        return stop_executor_actions

    def log_periodic_statistics(self):
        """
        BUG FIX #20: Log periodic statistics about bot performance.
        Called every 5 minutes to provide visibility into bot operation.
        """
        if self.last_stats_log_time is None:
            self.last_stats_log_time = self.current_timestamp
            return

        time_since_last_log = self.current_timestamp - self.last_stats_log_time
        if time_since_last_log < self.stats_log_interval:
            return

        self.last_stats_log_time = self.current_timestamp

        # Calculate total PnL and stats
        total_positions = len(self.active_funding_arbitrages)
        pending_positions = len(self.pending_funding_arbitrages)
        total_funding_payments = 0
        total_pnl = Decimal("0")

        for token, arb_info in self.active_funding_arbitrages.items():
            # Count funding payments
            total_funding_payments += len(arb_info["funding_payments"])

            # Calculate PnL for active positions
            executors = self.filter_executors(
                executors=self.get_all_executors(),
                filter_func=lambda x: x.id in arb_info["executors_ids"]
            )

            funding_payments_pnl = sum(
                funding_payment.amount if funding_payment.amount is not None else Decimal("0")
                for funding_payment in arb_info["funding_payments"]
            )

            executors_pnl = sum(
                executor.net_pnl_quote if executor.net_pnl_quote is not None else Decimal("0")
                for executor in executors
            )

            total_pnl += executors_pnl + funding_payments_pnl

        self.logger().info("=" * 80)
        self.logger().info("📊 PERIODIC STATISTICS REPORT")
        self.logger().info("=" * 80)
        self.logger().info(f"⏰ Uptime: {time_since_last_log / 60:.1f} minutes since last report")
        self.logger().info(f"📈 Active Positions: {total_positions}")
        self.logger().info(f"⏳ Pending Positions: {pending_positions}")
        self.logger().info(f"💰 Total Unrealized PnL: ${float(total_pnl):.2f}")
        self.logger().info(f"📬 Total Funding Payments Collected: {total_funding_payments}")
        if total_positions > 0:
            avg_funding_per_position = total_funding_payments / total_positions
            avg_pnl_per_position = float(total_pnl) / total_positions
            self.logger().info(f"📊 Average per Position:")
            self.logger().info(f"   • Funding Payments: {avg_funding_per_position:.1f}")
            self.logger().info(f"   • Unrealized PnL: ${avg_pnl_per_position:.2f}")
        self.logger().info(f"🔧 Rate Limiter Stats:")
        for exchange_stats in self.rate_limiter.get_all_stats():
            if exchange_stats['requests_last_second'] > 0:
                self.logger().info(f"   • {exchange_stats['exchange']}: {exchange_stats['requests_last_second']}/{exchange_stats['limit']} req/s ({exchange_stats['utilization']:.0f}%)")
        self.logger().info(f"⚠️  Error Count (since last reset): {self.error_count}")
        self.logger().info("=" * 80)

    def did_complete_funding_payment(self, funding_payment_completed_event: FundingPaymentCompletedEvent):
        """
        Based on the funding payment event received, check if one of the active arbitrages matches to add the event
        to the list.

        Note: We keep only the last 100 funding payments to prevent memory leak.
        """
        # BUG FIX #6: Use safe_split_trading_pair instead of direct split
        pair_parts = self.safe_split_trading_pair(funding_payment_completed_event.trading_pair)
        if pair_parts is None:
            self.logger().warning(f"Cannot parse trading_pair from funding payment event: {funding_payment_completed_event.trading_pair}")
            return

        token = pair_parts[0]
        if token in self.active_funding_arbitrages:
            self.active_funding_arbitrages[token]["funding_payments"].append(funding_payment_completed_event)
            # Prevent memory leak: keep only last 100 payments (enough for ~4 days on Hyperliquid, ~33 days on OKX)
            if len(self.active_funding_arbitrages[token]["funding_payments"]) > 100:
                self.active_funding_arbitrages[token]["funding_payments"] = self.active_funding_arbitrages[token]["funding_payments"][-100:]

    def get_position_executors_config(self, token, connector_1, connector_2, trade_side, position_size_quote: Decimal):
        # BUG FIX #1: Use safe_get_price instead of direct call
        trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
        trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)

        price_1 = self.safe_get_price(connector_1, trading_pair_1, PriceType.MidPrice)
        price_2 = self.safe_get_price(connector_2, trading_pair_2, PriceType.MidPrice)

        if price_1 is None or price_2 is None:
            self.logger().error(f"Price unavailable for {token} on {connector_1} or {connector_2}")
            # Return fallback configs with zero amounts (will be rejected later)
            return None, None

        if price_1 <= 0 or price_2 <= 0:
            self.logger().error(f"Invalid prices for {token}: {price_1}, {price_2}")
            return None, None

        position_amount_1 = position_size_quote / price_1
        position_amount_2 = position_size_quote / price_2

        position_executor_config_1 = PositionExecutorConfig(
            timestamp=self.current_timestamp,
            connector_name=connector_1,
            trading_pair=self.get_trading_pair_for_connector(token, connector_1),
            side=trade_side,
            amount=position_amount_1,
            leverage=self.config.leverage,
            triple_barrier_config=TripleBarrierConfig(open_order_type=OrderType.MARKET),
        )
        position_executor_config_2 = PositionExecutorConfig(
            timestamp=self.current_timestamp,
            connector_name=connector_2,
            trading_pair=self.get_trading_pair_for_connector(token, connector_2),
            side=TradeType.BUY if trade_side == TradeType.SELL else TradeType.SELL,
            amount=position_amount_2,
            leverage=self.config.leverage,
            triple_barrier_config=TripleBarrierConfig(open_order_type=OrderType.MARKET),
        )
        return position_executor_config_1, position_executor_config_2

    def format_status(self) -> str:
        original_status = super().format_status()
        funding_rate_status = []
        if self.ready_to_trade:
            all_funding_info = []
            all_best_paths = []
            for token in self.config.tokens:
                token_info = {"token": token}
                best_paths_info = {"token": token}
                funding_info_report = self.get_funding_info_by_token(token)

                # Skip if no funding info available
                if not funding_info_report or len(funding_info_report) < 2:
                    continue

                best_combination = self.get_most_profitable_combination(funding_info_report)

                # Add funding rates to token_info
                for connector_name, info in funding_info_report.items():
                    token_info[f"{connector_name} Rate (%)"] = self.get_normalized_funding_rate_in_seconds(funding_info_report, connector_name) * self.funding_profitability_interval * 100

                # Skip if no profitable combination found
                if best_combination is None:
                    best_paths_info["Best Path"] = "N/A"
                    best_paths_info["Best Rate Diff (%)"] = 0
                    best_paths_info["Trade Profitability (%)"] = 0
                    best_paths_info["Days Trade Prof"] = float('inf')
                    best_paths_info["Days to TP"] = float('inf')
                    best_paths_info["Min to Funding 1"] = 0
                    best_paths_info["Min to Funding 2"] = 0
                    all_funding_info.append(token_info)
                    all_best_paths.append(best_paths_info)
                    continue

                connector_1, connector_2, side, funding_rate_diff = best_combination
                position_size_quote = self.get_position_size_quote(connector_1, connector_2)
                profitability_after_fees = self.get_current_profitability_after_fees(token, connector_1, connector_2, side, position_size_quote)
                best_paths_info["Best Path"] = f"{connector_1}_{connector_2}"
                best_paths_info["Best Rate Diff (%)"] = funding_rate_diff * 100
                best_paths_info["Trade Profitability (%)"] = profitability_after_fees * 100
                # Protect against division by zero
                if funding_rate_diff > Decimal("0.0001"):
                    best_paths_info["Days Trade Prof"] = - profitability_after_fees / funding_rate_diff
                    best_paths_info["Days to TP"] = (self.config.profitability_to_take_profit - profitability_after_fees) / funding_rate_diff
                else:
                    best_paths_info["Days Trade Prof"] = float('inf')
                    best_paths_info["Days to TP"] = float('inf')

                # BUG FIX #10: Check if timestamp is None before operations
                try:
                    next_funding_c1 = funding_info_report[connector_1].next_funding_utc_timestamp
                    next_funding_c2 = funding_info_report[connector_2].next_funding_utc_timestamp

                    if next_funding_c1 is not None and self.current_timestamp is not None:
                        time_to_next_funding_info_c1 = next_funding_c1 - self.current_timestamp
                        best_paths_info["Min to Funding 1"] = time_to_next_funding_info_c1 / 60
                    else:
                        best_paths_info["Min to Funding 1"] = float('inf')

                    if next_funding_c2 is not None and self.current_timestamp is not None:
                        time_to_next_funding_info_c2 = next_funding_c2 - self.current_timestamp
                        best_paths_info["Min to Funding 2"] = time_to_next_funding_info_c2 / 60
                    else:
                        best_paths_info["Min to Funding 2"] = float('inf')
                except (TypeError, AttributeError) as e:
                    self.logger().warning(f"Error calculating time to next funding for {token}: {e}")
                    best_paths_info["Min to Funding 1"] = float('inf')
                    best_paths_info["Min to Funding 2"] = float('inf')

                all_funding_info.append(token_info)
                all_best_paths.append(best_paths_info)

            funding_rate_status.append(f"\n\n\nMin Funding Rate Profitability: {self.config.min_funding_rate_profitability:.2%}")
            funding_rate_status.append(f"Profitability to Take Profit: {self.config.profitability_to_take_profit:.2%}\n")
            funding_rate_status.append("Funding Rate Info (Funding Profitability in Days): ")

            # BUG FIX #14: Check if lists are not empty before creating DataFrames
            if all_funding_info:
                funding_rate_status.append(format_df_for_printout(df=pd.DataFrame(all_funding_info), table_format="psql",))
            else:
                funding_rate_status.append("No funding info available")

            if all_best_paths:
                funding_rate_status.append(format_df_for_printout(df=pd.DataFrame(all_best_paths), table_format="psql",))
            else:
                funding_rate_status.append("No profitable paths found")
            for token, funding_arbitrage_info in self.active_funding_arbitrages.items():
                long_connector = funding_arbitrage_info["connector_1"] if funding_arbitrage_info["side"] == TradeType.BUY else funding_arbitrage_info["connector_2"]
                short_connector = funding_arbitrage_info["connector_2"] if funding_arbitrage_info["side"] == TradeType.BUY else funding_arbitrage_info["connector_1"]
                funding_rate_status.append(f"Token: {token}")
                funding_rate_status.append(f"Long connector: {long_connector} | Short connector: {short_connector}")
                funding_rate_status.append(f"Funding Payments Collected: {funding_arbitrage_info['funding_payments']}")
                funding_rate_status.append(f"Executors: {funding_arbitrage_info['executors_ids']}")
                funding_rate_status.append("-" * 50 + "\n")
        return original_status + "\n".join(funding_rate_status)
