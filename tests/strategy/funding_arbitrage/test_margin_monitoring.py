"""
Unit tests for margin monitoring system.
"""

import unittest
from decimal import Decimal
import time

from hummingbot.strategy.funding_arbitrage.margin_monitoring import (
    MarginMonitor,
    MarginInfo,
    PositionMarginInfo,
    MarginStatus,
    ADLRisk,
    MarginAction,
    ExchangeMarginRequirements
)


class TestMarginInfo(unittest.TestCase):
    """Test MarginInfo dataclass and properties."""

    def test_margin_health_healthy(self):
        """Test healthy margin status."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("4000"),  # 40% utilization
            free_margin=Decimal("6000"),
            margin_ratio=Decimal("2.5"),  # 250%
            maintenance_margin=Decimal("2000"),
            initial_margin_req=Decimal("4000"),
            liquidation_price=None,
            timestamp=time.time()
        )

        self.assertEqual(margin_info.margin_health, MarginStatus.HEALTHY)

    def test_margin_health_warning(self):
        """Test warning margin status."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("5000"),
            free_margin=Decimal("5000"),
            margin_ratio=Decimal("1.8"),  # 180% - in warning zone
            maintenance_margin=Decimal("4000"),
            initial_margin_req=Decimal("5000"),
            liquidation_price=None,
            timestamp=time.time()
        )

        self.assertEqual(margin_info.margin_health, MarginStatus.WARNING)

    def test_margin_health_danger(self):
        """Test danger margin status."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("8000"),
            free_margin=Decimal("2000"),
            margin_ratio=Decimal("1.25"),  # 125% - danger zone
            maintenance_margin=Decimal("7000"),
            initial_margin_req=Decimal("8000"),
            liquidation_price=None,
            timestamp=time.time()
        )

        self.assertEqual(margin_info.margin_health, MarginStatus.DANGER)

    def test_margin_health_critical(self):
        """Test critical margin status."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("9500"),
            free_margin=Decimal("500"),
            margin_ratio=Decimal("1.05"),  # 105% - critical
            maintenance_margin=Decimal("9000"),
            initial_margin_req=Decimal("9500"),
            liquidation_price=None,
            timestamp=time.time()
        )

        self.assertEqual(margin_info.margin_health, MarginStatus.CRITICAL)

    def test_margin_health_liquidation_risk(self):
        """Test liquidation risk status."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("10500"),
            free_margin=Decimal("-500"),
            margin_ratio=Decimal("0.95"),  # 95% - liquidation risk!
            maintenance_margin=Decimal("10000"),
            initial_margin_req=Decimal("10500"),
            liquidation_price=Decimal("45000"),
            timestamp=time.time()
        )

        self.assertEqual(margin_info.margin_health, MarginStatus.LIQUIDATION_RISK)

    def test_utilization_percentage(self):
        """Test margin utilization calculation."""
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("3000"),
            free_margin=Decimal("7000"),
            margin_ratio=Decimal("3.33"),
            maintenance_margin=Decimal("2000"),
            initial_margin_req=Decimal("3000"),
            liquidation_price=None,
            timestamp=time.time()
        )

        # 3000 / 10000 = 30%
        self.assertEqual(margin_info.utilization_percentage, Decimal("30"))


class TestPositionMarginInfo(unittest.TestCase):
    """Test PositionMarginInfo dataclass and properties."""

    def test_distance_to_liquidation_long(self):
        """Test distance to liquidation for long position."""
        position_margin = PositionMarginInfo(
            position_id="pos_123",
            exchange="binance",
            trading_pair="BTC-USDT",
            side="long",
            size=Decimal("0.1"),
            notional_value=Decimal("5000"),
            leverage=Decimal("3"),
            initial_margin=Decimal("1666.67"),
            maintenance_margin=Decimal("500"),
            unrealized_pnl=Decimal("0"),
            liquidation_price=Decimal("40000"),
            current_mark_price=Decimal("50000"),
            adl_indicator=None,
            timestamp=time.time()
        )

        # For long: (current - liquidation) / current
        # (50000 - 40000) / 50000 = 0.2 = 20%
        distance = position_margin.distance_to_liquidation_pct
        self.assertIsNotNone(distance)
        self.assertEqual(distance, Decimal("20"))

    def test_distance_to_liquidation_short(self):
        """Test distance to liquidation for short position."""
        position_margin = PositionMarginInfo(
            position_id="pos_124",
            exchange="binance",
            trading_pair="BTC-USDT",
            side="short",
            size=Decimal("0.1"),
            notional_value=Decimal("5000"),
            leverage=Decimal("3"),
            initial_margin=Decimal("1666.67"),
            maintenance_margin=Decimal("500"),
            unrealized_pnl=Decimal("0"),
            liquidation_price=Decimal("60000"),
            current_mark_price=Decimal("50000"),
            adl_indicator=None,
            timestamp=time.time()
        )

        # For short: (liquidation - current) / current
        # (60000 - 50000) / 50000 = 0.2 = 20%
        distance = position_margin.distance_to_liquidation_pct
        self.assertIsNotNone(distance)
        self.assertEqual(distance, Decimal("20"))

    def test_distance_to_liquidation_none_when_no_price(self):
        """Test that distance returns None when prices unavailable."""
        position_margin = PositionMarginInfo(
            position_id="pos_125",
            exchange="binance",
            trading_pair="BTC-USDT",
            side="long",
            size=Decimal("0.1"),
            notional_value=Decimal("5000"),
            leverage=Decimal("3"),
            initial_margin=Decimal("1666.67"),
            maintenance_margin=Decimal("500"),
            unrealized_pnl=Decimal("0"),
            liquidation_price=None,  # No liquidation price
            current_mark_price=Decimal("50000"),
            adl_indicator=None,
            timestamp=time.time()
        )

        self.assertIsNone(position_margin.distance_to_liquidation_pct)


class TestExchangeMarginRequirements(unittest.TestCase):
    """Test ExchangeMarginRequirements."""

    def test_get_initial_margin_rate_no_tiers(self):
        """Test getting initial margin rate without tier system."""
        requirements = ExchangeMarginRequirements(
            exchange="binance",
            initial_margin_rates={'BTC-USDT': Decimal("0.1")},
            maintenance_margin_rates={'BTC-USDT': Decimal("0.05")},
            max_leverage={'BTC-USDT': Decimal("10")},
            liquidation_fee_rate=Decimal("0.005"),
            adl_enabled=True,
            margin_mode='cross',
            tier_system=None,
            last_updated=time.time()
        )

        rate = requirements.get_initial_margin_rate('BTC-USDT', Decimal("10000"))
        self.assertEqual(rate, Decimal("0.1"))

    def test_get_initial_margin_rate_with_tiers(self):
        """Test getting initial margin rate with tier system."""
        requirements = ExchangeMarginRequirements(
            exchange="binance",
            initial_margin_rates={'BTC-USDT': Decimal("0.1")},
            maintenance_margin_rates={'BTC-USDT': Decimal("0.05")},
            max_leverage={'BTC-USDT': Decimal("10")},
            liquidation_fee_rate=Decimal("0.005"),
            adl_enabled=True,
            margin_mode='cross',
            tier_system={
                'BTC-USDT': [
                    (Decimal("50000"), Decimal("0.01")),    # Up to 50k: 1%
                    (Decimal("250000"), Decimal("0.025")),  # Up to 250k: 2.5%
                    (Decimal("1000000"), Decimal("0.05")),  # Up to 1M: 5%
                ]
            },
            last_updated=time.time()
        )

        # Test small notional - should get tier 1
        rate_small = requirements.get_initial_margin_rate('BTC-USDT', Decimal("10000"))
        self.assertEqual(rate_small, Decimal("0.01"))

        # Test medium notional - should get tier 2
        rate_medium = requirements.get_initial_margin_rate('BTC-USDT', Decimal("100000"))
        self.assertEqual(rate_medium, Decimal("0.025"))

        # Test large notional - should get tier 3
        rate_large = requirements.get_initial_margin_rate('BTC-USDT', Decimal("500000"))
        self.assertEqual(rate_large, Decimal("0.05"))

    def test_empty_tier_system_fallback(self):
        """Test that empty tier system falls back to default."""
        requirements = ExchangeMarginRequirements(
            exchange="binance",
            initial_margin_rates={'BTC-USDT': Decimal("0.08")},
            maintenance_margin_rates={'BTC-USDT': Decimal("0.04")},
            max_leverage={'BTC-USDT': Decimal("10")},
            liquidation_fee_rate=Decimal("0.005"),
            adl_enabled=True,
            margin_mode='cross',
            tier_system={'BTC-USDT': []},  # Empty tier list
            last_updated=time.time()
        )

        rate = requirements.get_initial_margin_rate('BTC-USDT', Decimal("10000"))
        # Should fall back to initial_margin_rates
        self.assertEqual(rate, Decimal("0.08"))


class TestMarginMonitor(unittest.TestCase):
    """Test MarginMonitor functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = MarginMonitor(
            safety_buffer=Decimal("0.2"),
            max_allowed_leverage=Decimal("5"),
            auto_reduce_enabled=True
        )

    def test_calculate_safe_leverage(self):
        """Test safe leverage calculation."""
        # Set up exchange requirements
        requirements = ExchangeMarginRequirements(
            exchange="binance",
            initial_margin_rates={'BTC-USDT': Decimal("0.1")},
            maintenance_margin_rates={'BTC-USDT': Decimal("0.05")},
            max_leverage={'BTC-USDT': Decimal("10")},
            liquidation_fee_rate=Decimal("0.005"),
            adl_enabled=True,
            margin_mode='cross',
            tier_system=None,
            last_updated=time.time()
        )

        self.monitor.update_exchange_requirements(requirements)

        # Calculate safe leverage
        safe_leverage = self.monitor.calculate_safe_leverage(
            exchange="binance",
            symbol="BTC-USDT",
            notional=Decimal("10000")
        )

        # Safe leverage = 1 / (maintenance_margin * (1 + safety_buffer))
        # = 1 / (0.05 * 1.2) = 1 / 0.06 = 16.67
        # But capped by max_allowed_leverage (5) and exchange max (10)
        self.assertEqual(safe_leverage, Decimal("5"))

    def test_update_margin_info_triggers_alerts(self):
        """Test that updating margin info triggers alerts for critical status."""
        alert_triggered = []

        def alert_callback(status, data):
            alert_triggered.append((status, data))

        self.monitor.register_alert_callback(alert_callback)

        # Create critical margin info
        margin_info = MarginInfo(
            exchange="binance",
            account_id="main",
            total_equity=Decimal("10000"),
            used_margin=Decimal("9500"),
            free_margin=Decimal("500"),
            margin_ratio=Decimal("1.05"),
            maintenance_margin=Decimal("9000"),
            initial_margin_req=Decimal("9500"),
            liquidation_price=Decimal("45000"),
            timestamp=time.time()
        )

        self.monitor.update_margin_info(margin_info)

        # Should have triggered alert
        self.assertGreater(len(alert_triggered), 0)
        status, data = alert_triggered[0]
        self.assertIn(status, [MarginStatus.CRITICAL, MarginStatus.DANGER])


if __name__ == '__main__':
    unittest.main()
