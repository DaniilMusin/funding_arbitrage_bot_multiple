"""
Configuration map for funding arbitrage strategy.
"""

from decimal import Decimal
from typing import Optional

from hummingbot.client.config.config_validators import (
    validate_connector,
    validate_decimal,
    validate_derivative,
    validate_int,
    validate_market_trading_pair,
)
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.settings import AllConnectorSettings, required_exchanges, requried_connector_trading_pairs


def exchange_on_validated(value: str) -> None:
    """Add exchange to required exchanges."""
    required_exchanges.add(value)


def trading_pair_validator(value: str) -> Optional[str]:
    """Validate trading pair for all configured exchanges."""
    # Get all configured exchanges
    exchanges = []
    for i in range(1, 6):  # Support up to 5 exchanges
        key = f"exchange_{i}"
        if key in funding_arbitrage_config_map and funding_arbitrage_config_map[key].value:
            exchanges.append(funding_arbitrage_config_map[key].value)

    # Validate pair exists on at least one exchange
    for exchange in exchanges:
        result = validate_market_trading_pair(exchange, value)
        if result is None:
            return None

    return f"Invalid trading pair {value}"


def trading_pair_on_validated(value: str) -> None:
    """Add trading pair to required pairs for all exchanges."""
    for i in range(1, 6):
        key = f"exchange_{i}"
        if key in funding_arbitrage_config_map and funding_arbitrage_config_map[key].value:
            exchange = funding_arbitrage_config_map[key].value
            if exchange not in requried_connector_trading_pairs:
                requried_connector_trading_pairs[exchange] = []
            if value not in requried_connector_trading_pairs[exchange]:
                requried_connector_trading_pairs[exchange].append(value)


def trading_pairs_validator(value: str) -> Optional[str]:
    """Validate comma-separated trading pairs for all configured exchanges."""
    if not value:
        return "At least one trading pair is required"

    pairs = [pair.strip() for pair in value.split(",") if pair.strip()]
    if not pairs:
        return "At least one trading pair is required"

    for pair in pairs:
        if trading_pair_validator(pair) is not None:
            return f"Invalid trading pair {pair}"

    return None


def trading_pairs_on_validated(value: str) -> None:
    """Add trading pairs to required pairs for all exchanges."""
    if not value:
        return
    pairs = [pair.strip() for pair in value.split(",") if pair.strip()]
    for pair in pairs:
        trading_pair_on_validated(pair)


def trading_pair_prompt() -> str:
    """Generate trading pair prompt."""
    exchanges = []
    for i in range(1, 6):
        key = f"exchange_{i}"
        if key in funding_arbitrage_config_map and funding_arbitrage_config_map[key].value:
            exchanges.append(funding_arbitrage_config_map[key].value)

    if exchanges:
        example = AllConnectorSettings.get_example_pairs().get(exchanges[0])
        return f"Enter the token trading pair for funding arbitrage{f' (e.g. {example})' if example else ''} >>> "
    return "Enter the token trading pair >>> "


funding_arbitrage_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="funding_arbitrage"
    ),

    # Exchange configurations (support up to 5 exchanges)
    "exchange_1": ConfigVar(
        key="exchange_1",
        prompt="Enter your first perpetual exchange >>> ",
        prompt_on_new=True,
        validator=lambda v: validate_derivative(v) if v else None,
        on_validated=exchange_on_validated,
        is_connect_key=True
    ),
    "exchange_2": ConfigVar(
        key="exchange_2",
        prompt="Enter your second perpetual exchange (or leave empty if only one) >>> ",
        required_if=lambda: False,
        validator=lambda v: validate_derivative(v) if v else None,
        on_validated=exchange_on_validated,
        is_connect_key=True
    ),
    "exchange_3": ConfigVar(
        key="exchange_3",
        prompt="Enter your third perpetual exchange (optional) >>> ",
        required_if=lambda: False,
        validator=lambda v: validate_derivative(v) if v else None,
        on_validated=exchange_on_validated,
        is_connect_key=True
    ),

    # Auto pair selection mode
    "auto_select_pairs": ConfigVar(
        key="auto_select_pairs",
        prompt="Enable automatic trading pair selection? (Yes/No) >>> ",
        default=True,
        type_str="bool",
        prompt_on_new=True
    ),

    # Trading pair (only if not auto-selecting)
    "trading_pair": ConfigVar(
        key="trading_pair",
        prompt=trading_pair_prompt,
        required_if=lambda: not funding_arbitrage_config_map.get("auto_select_pairs").value,
        validator=trading_pair_validator,
        on_validated=trading_pair_on_validated
    ),
    "candidate_trading_pairs": ConfigVar(
        key="candidate_trading_pairs",
        prompt="Enter candidate trading pairs for auto selection (comma-separated) >>> ",
        required_if=lambda: funding_arbitrage_config_map.get("auto_select_pairs").value,
        validator=trading_pairs_validator,
        on_validated=trading_pairs_on_validated
    ),

    # Auto selection parameters
    "max_trading_pairs": ConfigVar(
        key="max_trading_pairs",
        prompt="How many trading pairs to trade simultaneously (if auto-selecting)? >>> ",
        default=3,
        required_if=lambda: funding_arbitrage_config_map.get("auto_select_pairs").value,
        type_str="int",
        validator=lambda v: validate_int(v, min_value=1, max_value=10, inclusive=True)
    ),
    "pair_scan_interval": ConfigVar(
        key="pair_scan_interval",
        prompt="How often to rescan pairs for profitability (in seconds, if auto-selecting)? >>> ",
        default=300,
        required_if=lambda: funding_arbitrage_config_map.get("auto_select_pairs").value,
        type_str="int",
        validator=lambda v: validate_int(v, min_value=60, inclusive=True)
    ),

    # Position sizing
    "order_amount": ConfigVar(
        key="order_amount",
        prompt="What is the order amount per arbitrage position (in quote currency)? >>> ",
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False),
        prompt_on_new=True
    ),

    # Entry criteria
    "min_funding_rate_diff": ConfigVar(
        key="min_funding_rate_diff",
        prompt="What is the minimum funding rate difference to enter a position (in %)? >>> ",
        default=Decimal("0.03"),
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False)
    ),
    "min_edge_required": ConfigVar(
        key="min_edge_required",
        prompt="What is the minimum total edge required (in %)? >>> ",
        default=Decimal("0.05"),
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False)
    ),

    # Risk management
    "max_notional_per_exchange": ConfigVar(
        key="max_notional_per_exchange",
        prompt="What is the maximum notional value per exchange (in USD)? >>> ",
        default=Decimal("50000"),
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False)
    ),
    "max_total_notional": ConfigVar(
        key="max_total_notional",
        prompt="What is the maximum total notional value across all exchanges (in USD)? >>> ",
        default=Decimal("200000"),
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("0"), inclusive=False)
    ),
    "max_leverage": ConfigVar(
        key="max_leverage",
        prompt="What is the maximum leverage to use? >>> ",
        default=Decimal("5"),
        type_str="decimal",
        validator=lambda v: validate_decimal(v, Decimal("1"), Decimal("20"))
    ),

    # Timing
    "funding_check_interval": ConfigVar(
        key="funding_check_interval",
        prompt="How often to check funding rates (in seconds)? >>> ",
        default=60,
        type_str="int",
        validator=lambda v: validate_int(v, min_value=10, inclusive=True)
    ),
    "min_position_hold_time": ConfigVar(
        key="min_position_hold_time",
        prompt="Minimum position hold time (in minutes)? >>> ",
        default=10,
        type_str="int",
        validator=lambda v: validate_int(v, min_value=1, inclusive=True)
    ),

    # Safety
    "emergency_stop_on_critical": ConfigVar(
        key="emergency_stop_on_critical",
        prompt="Enable emergency stop on critical issues? (Yes/No) >>> ",
        default=True,
        type_str="bool"
    ),
}
