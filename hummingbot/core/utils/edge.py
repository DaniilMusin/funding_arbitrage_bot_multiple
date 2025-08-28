from dataclasses import dataclass
from typing import Optional, Dict

from hummingbot.core.observability.metrics import get_metrics_collector


@dataclass
class EdgeInputs:
    expected_funding: float
    fees_perp: float
    fees_spot: float
    borrow_cost: float
    slippage_buffer: float


def compute_edge(inputs: EdgeInputs) -> float:
    """Compute edge as per formula.
    edge = expected_funding - (fees_perp + fees_spot) - borrow_cost - slippage_buffer
    """
    return (
        float(inputs.expected_funding)
        - (float(inputs.fees_perp) + float(inputs.fees_spot))
        - float(inputs.borrow_cost)
        - float(inputs.slippage_buffer)
    )


def record_edge_metrics(exchange: str, trading_pair: str, inputs: EdgeInputs):
    mc = get_metrics_collector()
    value = compute_edge(inputs)
    mc.set_edge(exchange, trading_pair, value)
    mc.set_edge_component(exchange, trading_pair, "expected_funding", inputs.expected_funding)
    mc.set_edge_component(exchange, trading_pair, "fees_perp", inputs.fees_perp)
    mc.set_edge_component(exchange, trading_pair, "fees_spot", inputs.fees_spot)
    mc.set_edge_component(exchange, trading_pair, "borrow_cost", inputs.borrow_cost)
    mc.set_edge_component(exchange, trading_pair, "slippage_buffer", inputs.slippage_buffer)
    return value


def set_funding_time_to_next(exchange: str, seconds: float):
    get_metrics_collector().set_funding_time_to_next(exchange, seconds)

