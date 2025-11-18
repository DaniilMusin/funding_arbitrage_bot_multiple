"""
Start script for funding arbitrage strategy.
Initializes the strategy with configuration from config_map.
"""

from decimal import Decimal
from typing import Dict, List

from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.strategy.funding_arbitrage.funding_arbitrage_strategy import (
    FundingArbitrageConfig,
    FundingArbitrageStrategy,
)
from hummingbot.strategy.funding_arbitrage.funding_arbitrage_config_map import funding_arbitrage_config_map


def start(self):
    """
    Initialize and start the funding arbitrage strategy.

    This function is called by hummingbot when starting the strategy from CLI.
    """
    # Collect exchanges
    exchanges: Dict[str, ConnectorBase] = {}
    trading_pairs: List[str] = []

    # Get trading pair
    trading_pair = funding_arbitrage_config_map.get("trading_pair").value

    # Collect all configured exchanges
    exchange_connectors = []
    for i in range(1, 6):  # Support up to 5 exchanges
        key = f"exchange_{i}"
        if key in funding_arbitrage_config_map:
            exchange_name = funding_arbitrage_config_map.get(key).value
            if exchange_name:
                exchange_connectors.append((exchange_name.lower(), [trading_pair]))

    if not exchange_connectors:
        self.logger().error("No exchanges configured for funding arbitrage")
        return

    # Initialize markets
    self._initialize_markets(exchange_connectors)

    # Build exchanges dict
    for exchange_name, _ in exchange_connectors:
        if exchange_name in self.markets:
            exchanges[exchange_name] = self.markets[exchange_name]

    # Get configuration values
    order_amount = funding_arbitrage_config_map.get("order_amount").value
    min_funding_rate_diff = funding_arbitrage_config_map.get("min_funding_rate_diff").value / Decimal("100")
    min_edge_required = funding_arbitrage_config_map.get("min_edge_required").value / Decimal("100")
    max_notional_per_exchange = funding_arbitrage_config_map.get("max_notional_per_exchange").value
    max_total_notional = funding_arbitrage_config_map.get("max_total_notional").value
    max_leverage = funding_arbitrage_config_map.get("max_leverage").value
    funding_check_interval = funding_arbitrage_config_map.get("funding_check_interval").value
    min_position_hold_time = funding_arbitrage_config_map.get("min_position_hold_time").value
    emergency_stop = funding_arbitrage_config_map.get("emergency_stop_on_critical").value

    # Create strategy configuration
    config = FundingArbitrageConfig(
        min_edge_required=min_edge_required,
        min_funding_rate_diff=min_funding_rate_diff,
        min_position_hold_time_minutes=min_position_hold_time,
        max_notional_per_exchange=max_notional_per_exchange,
        max_total_notional=max_total_notional,
        max_leverage=max_leverage,
        funding_check_interval_seconds=funding_check_interval,
        emergency_stop_on_critical_issues=emergency_stop,
        order_amount=order_amount,
    )

    # Create and initialize strategy
    self.strategy = FundingArbitrageStrategy(
        exchanges=exchanges,
        config=config,
        trading_pairs=[trading_pair],
    )

    self.logger().info(
        f"Funding arbitrage strategy initialized:\n"
        f"  Exchanges: {', '.join(exchanges.keys())}\n"
        f"  Trading pair: {trading_pair}\n"
        f"  Order amount: {order_amount}\n"
        f"  Min funding rate diff: {min_funding_rate_diff:.2%}\n"
        f"  Min edge required: {min_edge_required:.2%}\n"
        f"  Max leverage: {max_leverage}x"
    )
