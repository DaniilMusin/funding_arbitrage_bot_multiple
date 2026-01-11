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

    # Get configuration mode
    auto_select_pairs = funding_arbitrage_config_map.get("auto_select_pairs").value

    # Get trading pair(s)
    if auto_select_pairs:
        # Auto mode: scan within provided candidate pairs
        trading_pair = None
        candidate_pairs_value = funding_arbitrage_config_map.get("candidate_trading_pairs").value
        if candidate_pairs_value:
            trading_pairs = [
                pair.strip()
                for pair in str(candidate_pairs_value).split(",")
                if pair.strip()
            ]
        if not trading_pairs:
            self.logger().error(
                "Auto pair selection requires candidate_trading_pairs to be set."
            )
            return
        self.logger().info(
            "Auto pair selection enabled - scanning candidate pairs: "
            f"{', '.join(trading_pairs)}"
        )
    else:
        # Manual mode: use specified pair
        trading_pair = funding_arbitrage_config_map.get("trading_pair").value
        trading_pairs = [trading_pair]

    # Collect all configured exchanges
    exchange_connectors = []
    for i in range(1, 6):  # Support up to 5 exchanges
        key = f"exchange_{i}"
        if key in funding_arbitrage_config_map:
            exchange_name = funding_arbitrage_config_map.get(key).value
            if exchange_name:
                # In auto mode, don't specify pairs - will be discovered
                pairs_to_init = trading_pairs if trading_pairs else ([trading_pair] if trading_pair else [])
                exchange_connectors.append((exchange_name.lower(), pairs_to_init))

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

    # Auto selection parameters
    max_trading_pairs = funding_arbitrage_config_map.get("max_trading_pairs").value if auto_select_pairs else 1
    pair_scan_interval = funding_arbitrage_config_map.get("pair_scan_interval").value if auto_select_pairs else 300

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
        auto_select_pairs=auto_select_pairs,
        max_trading_pairs=max_trading_pairs,
        pair_scan_interval_seconds=pair_scan_interval,
    )

    # Create and initialize strategy
    self.strategy = FundingArbitrageStrategy(
        exchanges=exchanges,
        config=config,
        trading_pairs=trading_pairs,  # Empty if auto mode
    )

    # Log initialization
    if auto_select_pairs:
        self.logger().info(
            f"Funding arbitrage strategy initialized (AUTO MODE):\n"
            f"  Exchanges: {', '.join(exchanges.keys())}\n"
            f"  Candidate pairs: {', '.join(trading_pairs)}\n"
            f"  Max trading pairs: {max_trading_pairs}\n"
            f"  Pair scan interval: {pair_scan_interval}s\n"
            f"  Order amount: {order_amount}\n"
            f"  Min funding rate diff: {min_funding_rate_diff:.2%}\n"
            f"  Min edge required: {min_edge_required:.2%}\n"
            f"  Max leverage: {max_leverage}x"
        )
    else:
        self.logger().info(
            f"Funding arbitrage strategy initialized (MANUAL MODE):\n"
            f"  Exchanges: {', '.join(exchanges.keys())}\n"
            f"  Trading pair: {trading_pair}\n"
            f"  Order amount: {order_amount}\n"
            f"  Min funding rate diff: {min_funding_rate_diff:.2%}\n"
            f"  Min edge required: {min_edge_required:.2%}\n"
            f"  Max leverage: {max_leverage}x"
        )
