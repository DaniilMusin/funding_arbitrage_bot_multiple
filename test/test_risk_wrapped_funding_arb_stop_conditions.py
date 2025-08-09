import logging
import sys
import types
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from scripts.risk_hooks import RiskWrappedFundingArb


# Create lightweight stubs for heavy hummingbot modules before importing the strategy
hb_app_module = types.ModuleType("hummingbot.client.hummingbot_application")


class DummyHBApp:
    def stop(self):
        pass


_dummy_app = DummyHBApp()


class HBAppCls:
    @classmethod
    def main_application(cls):
        return _dummy_app


hb_app_module.HummingbotApplication = HBAppCls
sys.modules['hummingbot.client.hummingbot_application'] = hb_app_module

connector_module = types.ModuleType("hummingbot.connector.connector_base")


class ConnectorBase:
    pass


connector_module.ConnectorBase = ConnectorBase
sys.modules['hummingbot.connector.connector_base'] = connector_module

v2_module = types.ModuleType("scripts.v2_funding_rate_arb")


class DummyBase:
    def __init__(self, connectors, config):
        self.connectors = connectors
        self.config = config
        self.controllers = {}
        self.controller_reports = {}
        self._current_timestamp = 0

    @property
    def current_timestamp(self):
        return self._current_timestamp

    def _set_current_timestamp(self, ts):
        self._current_timestamp = ts

    def get_performance_report(self, controller_id):
        return self.controller_reports.get(controller_id, {}).get("performance")

    def on_tick(self):
        pass

    def logger(self):
        logger = logging.getLogger("dummy")
        logger.setLevel(1)
        return logger


class DummyConfig:
    pass


v2_module.FundingRateArbitrage = DummyBase
v2_module.FundingRateArbitrageConfig = DummyConfig
sys.modules['scripts.v2_funding_rate_arb'] = v2_module


class PerformanceReport:
    def __init__(self, realized_pnl_quote: Decimal):
        self.realized_pnl_quote = realized_pnl_quote


class RiskWrappedFundingArbStopTest(unittest.TestCase):
    def setUp(self):
        self.strategy = RiskWrappedFundingArb(connectors={}, config=DummyConfig())
        self.strategy.controllers = {"c1": MagicMock()}
        self.strategy._set_current_timestamp(0)
        self.strategy._day_start_ts = 0

    def _set_pnl(self, pnl: Decimal):
        self.strategy.controller_reports = {"c1": {"performance": PerformanceReport(pnl)}}

    def test_stop_on_profit_limit(self):
        self._set_pnl(self.strategy.DAILY_PROFIT_LIMIT_USD + Decimal("1"))
        with patch.object(HBAppCls, 'main_application', return_value=_dummy_app) as main_app:
            with patch.object(_dummy_app, 'stop') as stop_mock:
                self.strategy._check_stop_loss()
                stop_mock.assert_called_once()

    def test_stop_on_loss_limit(self):
        self._set_pnl(-(self.strategy.DAILY_LOSS_LIMIT_USD + Decimal("1")))
        with patch.object(HBAppCls, 'main_application', return_value=_dummy_app) as main_app:
            with patch.object(_dummy_app, 'stop') as stop_mock:
                self.strategy._check_stop_loss()
                stop_mock.assert_called_once()


if __name__ == '__main__':
    unittest.main()
