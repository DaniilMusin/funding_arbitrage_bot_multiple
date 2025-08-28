from decimal import Decimal
import datetime as dt

from hummingbot.core.utils.edge import EdgeInputs, compute_edge
from hummingbot.core.utils.funding_schedule import seconds_to_next_funding


def test_compute_edge_formula():
    inputs = EdgeInputs(
        expected_funding=0.002,
        fees_perp=0.0004,
        fees_spot=0.0002,
        borrow_cost=0.0003,
        slippage_buffer=0.0005,
    )
    edge = compute_edge(inputs)
    assert abs(edge - (0.002 - (0.0004 + 0.0002) - 0.0003 - 0.0005)) < 1e-12


def test_seconds_to_next_funding_binance():
    # 07:59 UTC should be ~60s to 08:00
    now = dt.datetime(2024, 1, 1, 7, 59, 0, tzinfo=dt.timezone.utc)
    seconds = seconds_to_next_funding("binance_perpetual", now=now, conf_path="/workspace/conf/funding_schedules.yaml")
    assert 0 < seconds <= 120
