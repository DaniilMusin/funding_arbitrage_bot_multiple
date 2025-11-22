from datetime import datetime
from decimal import Decimal
from typing import Dict

from hummingbot.client.hummingbot_application import HummingbotApplication
from hummingbot.connector.connector_base import ConnectorBase

from scripts.v2_funding_rate_arb import (
    FundingRateArbitrage as FundingRateArbStrategy,
    FundingRateArbitrageConfig,
)


class RiskWrappedFundingArb(FundingRateArbStrategy):
    """Funding rate arbitrage strategy with basic risk management hooks."""

    DAILY_PROFIT_LIMIT_USD: Decimal = Decimal("500")
    DAILY_LOSS_LIMIT_USD: Decimal = Decimal("500")
    WS_LATENCY_LIMIT_SEC: int = 60

    def __init__(self, connectors: Dict[str, ConnectorBase], config: FundingRateArbitrageConfig):
        super().__init__(connectors, config)
        self._day_start_ts = self.current_timestamp

    def on_tick(self):
        super().on_tick()
        self._check_stop_loss()
        self._check_ws_latency()

    def _reset_day_if_needed(self):
        current_day = datetime.utcfromtimestamp(self.current_timestamp).date()
        start_day = datetime.utcfromtimestamp(self._day_start_ts).date()
        if current_day != start_day:
            self._day_start_ts = self.current_timestamp

    def _aggregate_realized_pnl(self) -> Decimal:
        realized = Decimal("0")
        for controller_id in self.controllers.keys():
            report = self.get_performance_report(controller_id)
            if report is not None:
                realized += report.realized_pnl_quote
        return realized

    def _check_stop_loss(self):
        self._reset_day_if_needed()
        realized = self._aggregate_realized_pnl()
        if realized >= self.DAILY_PROFIT_LIMIT_USD:
            self.logger().info("Daily profit limit reached. Stopping strategy.")
            HummingbotApplication.main_application().stop()
        elif realized <= -self.DAILY_LOSS_LIMIT_USD:
            self.logger().info("Daily loss limit reached. Stopping strategy.")
            HummingbotApplication.main_application().stop()

    def _check_ws_latency(self):
        threshold = self.WS_LATENCY_LIMIT_SEC
        for name, connector in self.connectors.items():
            try:
                last = connector.user_stream_tracker.data_source.last_recv_time
            except (AttributeError, TypeError) as e:
                # Connector may not have user stream tracker or data source
                self.logger().debug(f"Could not check WS latency for {name}: {e}")
                continue
            except Exception as e:
                # Log unexpected errors but continue checking other connectors
                self.logger().warning(f"Unexpected error checking WS latency for {name}: {e}")
                continue
            if last > 0 and self.current_timestamp - last > threshold:
                self.logger().warning(f"WebSocket latency on {name} over {threshold}s. Stopping strategy.")
                HummingbotApplication.main_application().stop()
                break
