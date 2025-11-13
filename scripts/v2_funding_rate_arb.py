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
        self.stopped_funding_arbitrages = {token: [] for token in self.config.tokens}

    def start(self, clock: Clock, timestamp: float) -> None:
        """
        Start the strategy.
        :param clock: Clock to use.
        :param timestamp: Current time.
        """
        self._last_timestamp = timestamp
        self.apply_initial_setting()

    def apply_initial_setting(self):
        for connector_name, connector in self.connectors.items():
            if self.is_perpetual(connector_name):
                # Check if exchange only supports ONEWAY mode, otherwise use HEDGE for better risk management
                position_mode = PositionMode.ONEWAY if connector_name in self.oneway_only_exchanges else PositionMode.HEDGE
                connector.set_position_mode(position_mode)
                for trading_pair in self.market_data_provider.get_trading_pairs(connector_name):
                    connector.set_leverage(trading_pair, self.config.leverage)

    def get_connectors_in_use(self) -> Set[str]:
        connectors = set()
        for info in self.active_funding_arbitrages.values():
            connectors.add(info["connector_1"])
            connectors.add(info["connector_2"])
        return connectors

    # ========================================
    # SAFE API WRAPPERS (Bug fixes #1-10)
    # ========================================

    def safe_get_price(self, connector_name: str, trading_pair: str, price_type=PriceType.MidPrice) -> Decimal | None:
        """
        Safe wrapper for get_price_by_type with error handling.
        Returns None if price unavailable instead of crashing.
        """
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
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting price for {connector_name} {trading_pair}: {e}")
            return None

    def safe_get_price_for_volume(self, connector_name: str, trading_pair: str, quote_volume: Decimal, is_buy: bool) -> Decimal | None:
        """Safe wrapper for get_price_for_quote_volume with error handling."""
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
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting price for volume {connector_name} {trading_pair}: {e}")
            return None

    def safe_get_balance(self, connector_name: str, currency: str) -> Decimal | None:
        """Safe wrapper for get_available_balance with error handling."""
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
            return None
        except Exception as e:
            self.logger().error(f"Unexpected error getting balance for {connector_name} {currency}: {e}")
            return None

    def safe_get_fee(self, connector_name: str, base_currency: str, quote_currency: str,
                    order_type: OrderType, order_side: TradeType, amount: Decimal,
                    price: Decimal, is_maker: bool, position_action: PositionAction) -> Decimal | None:
        """Safe wrapper for get_fee with error handling."""
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
            return Decimal("0.001")  # Fallback to conservative estimate
        except Exception as e:
            self.logger().error(f"Unexpected error getting fee for {connector_name}: {e}")
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

                    current_profitability = self.get_current_profitability_after_fees(
                        token, connector_1, connector_2, trade_side, position_size_quote
                    )

                    # SAFETY CHECK 2: Slippage protection
                    trading_pair_1 = self.get_trading_pair_for_connector(token, connector_1)
                    trading_pair_2 = self.get_trading_pair_for_connector(token, connector_2)
                    expected_price_1 = Decimal(self.market_data_provider.get_price_by_type(
                        connector_name=connector_1, trading_pair=trading_pair_1, price_type=PriceType.MidPrice
                    ))
                    expected_price_2 = Decimal(self.market_data_provider.get_price_by_type(
                        connector_name=connector_2, trading_pair=trading_pair_2, price_type=PriceType.MidPrice
                    ))

                    slippage_ok, slippage_msg = self.check_slippage(
                        token, connector_1, connector_2, expected_price_1, expected_price_2, position_size_quote
                    )
                    if not slippage_ok:
                        self.logger().warning(f"Skipping {token}: {slippage_msg}")
                        continue
                    elif slippage_msg:
                        self.logger().info(f"{token}: {slippage_msg}")
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

                    self.active_funding_arbitrages[token] = {
                        "connector_1": connector_1,
                        "connector_2": connector_2,
                        "executors_ids": [position_executor_config_1.id, position_executor_config_2.id],
                        "side": trade_side,
                        "funding_payments": [],
                        "position_size_quote": position_size_quote,
                    }
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

    def stop_actions_proposal(self) -> List[StopExecutorAction]:
        """
        Once the funding rate arbitrage is created we are going to control the funding payments pnl and the current
        pnl of each of the executors at the cost of closing the open position at market.
        If that PNL is greater than the profitability_to_take_profit

        SAFETY: Also monitors position hedge and triggers emergency close if imbalanced.
        """
        stop_executor_actions = []
        tokens_to_remove = []
        for token, funding_arbitrage_info in self.active_funding_arbitrages.items():
            # SAFETY CHECK: Validate position hedge (continuous monitoring)
            if self.config.position_validation_enabled:
                is_hedged, hedge_msg = self.validate_position_hedge(token)
                if not is_hedged:
                    if self.config.emergency_close_on_imbalance:
                        self.logger().error(f"EMERGENCY CLOSE for {token}: {hedge_msg}")
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
                self.logger().info(f"Take profit profitability reached for {token}, stopping executors")
                self.stopped_funding_arbitrages[token].append(funding_arbitrage_info)
                # Prevent memory leak: keep only last 10 stopped arbitrages per token
                if len(self.stopped_funding_arbitrages[token]) > 10:
                    self.stopped_funding_arbitrages[token] = self.stopped_funding_arbitrages[token][-10:]
                stop_executor_actions.extend([StopExecutorAction(executor_id=executor.id) for executor in executors])
                tokens_to_remove.append(token)
            elif current_funding_condition:
                self.logger().info(f"Funding rate difference reached for stop loss for {token}, stopping executors")
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
