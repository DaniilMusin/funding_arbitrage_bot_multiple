"""
Unit tests for edge decomposition system.
"""

import unittest
from decimal import Decimal
import time

from hummingbot.strategy.funding_arbitrage.edge_decomposition import (
    EdgeCalculator,
    EdgeTracker,
    EdgeDecomposition
)


class TestEdgeCalculator(unittest.TestCase):
    """Test EdgeCalculator functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.calculator = EdgeCalculator(
            min_edge_required=Decimal("0.0005"),
            settlement_buffer_bps=Decimal("0.0001")
        )

    def test_profitable_opportunity(self):
        """Test calculation of a profitable opportunity."""
        edge = self.calculator.calculate_edge(
            trading_pair="BTC-USDT",
            exchange_long="binance",
            exchange_short="bybit",
            funding_rate_long=Decimal("0.0001"),  # 0.01% long pays
            funding_rate_short=Decimal("0.0005"),  # 0.05% short receives
            notional_amount=Decimal("10000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'bybit': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'BTC': Decimal("0.0001"), 'USDT': Decimal("0.00005")},
            slippage_estimates={'binance': Decimal("0.0003"), 'bybit': Decimal("0.0003")},
            leverage_long=Decimal("1"),
            leverage_short=Decimal("1"),
            funding_period_hours=Decimal("8")
        )

        # Check that edge was calculated
        self.assertIsNotNone(edge)
        self.assertIsInstance(edge, EdgeDecomposition)

        # Check basic properties
        self.assertEqual(edge.trading_pair, "BTC-USDT")
        self.assertEqual(edge.exchange_long, "binance")
        self.assertEqual(edge.exchange_short, "bybit")

        # Funding differential should be positive (short receives more than long pays)
        expected_funding_diff = Decimal("0.0005") - Decimal("0.0001")
        self.assertEqual(edge.expected_funding_rate, expected_funding_diff)

        # Expected funding PnL should be positive
        expected_funding_pnl = expected_funding_diff * Decimal("10000")
        self.assertEqual(edge.expected_funding_pnl, expected_funding_pnl)

        # Total edge should account for fees and costs
        self.assertIsInstance(edge.total_edge, Decimal)

        # Check profitability
        # With positive funding diff and reasonable fees, should be profitable
        self.assertTrue(edge.is_profitable)
        self.assertGreater(edge.total_edge, edge.min_edge_required)

    def test_unprofitable_opportunity_negative_funding(self):
        """Test that negative funding differential results in unprofitable edge."""
        edge = self.calculator.calculate_edge(
            trading_pair="ETH-USDT",
            exchange_long="binance",
            exchange_short="okx",
            funding_rate_long=Decimal("0.0005"),  # 0.05% long pays
            funding_rate_short=Decimal("0.0001"),  # 0.01% short receives
            notional_amount=Decimal("5000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'okx': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'ETH': Decimal("0.0001"), 'USDT': Decimal("0.00005")},
            slippage_estimates={'binance': Decimal("0.0003"), 'okx': Decimal("0.0003")},
            leverage_long=Decimal("1"),
            leverage_short=Decimal("1")
        )

        # Negative funding differential (long pays more than short receives)
        self.assertEqual(edge.expected_funding_rate, Decimal("0.0001") - Decimal("0.0005"))
        self.assertLess(edge.expected_funding_pnl, 0)

        # Should be unprofitable
        self.assertFalse(edge.is_profitable)
        self.assertLess(edge.total_edge, edge.min_edge_required)

    def test_edge_with_leverage(self):
        """Test edge calculation with leveraged positions."""
        edge = self.calculator.calculate_edge(
            trading_pair="BTC-USDT",
            exchange_long="binance",
            exchange_short="bybit",
            funding_rate_long=Decimal("0.0001"),
            funding_rate_short=Decimal("0.0005"),
            notional_amount=Decimal("10000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'bybit': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'BTC': Decimal("0.0002"), 'USDT': Decimal("0.0001")},
            slippage_estimates={'binance': Decimal("0.0003"), 'bybit': Decimal("0.0003")},
            leverage_long=Decimal("3"),
            leverage_short=Decimal("3"),
            funding_period_hours=Decimal("8")
        )

        # With 3x leverage, borrow costs should be higher
        # Borrow breakdown should have entries for leveraged positions
        self.assertGreater(len(edge.borrow_breakdown), 0)

        # Edge should still be calculated
        self.assertIsNotNone(edge.total_edge)

        # Leverage should increase risk
        self.assertGreater(edge.hedge_gap_risk, Decimal("0"))

    def test_fees_breakdown(self):
        """Test that fees are properly broken down."""
        edge = self.calculator.calculate_edge(
            trading_pair="BTC-USDT",
            exchange_long="binance",
            exchange_short="bybit",
            funding_rate_long=Decimal("0.0001"),
            funding_rate_short=Decimal("0.0005"),
            notional_amount=Decimal("10000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'bybit': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'BTC': Decimal("0.0001"), 'USDT': Decimal("0.00005")},
            slippage_estimates={'binance': Decimal("0.0003"), 'bybit': Decimal("0.0003")}
        )

        # Should have fees for both open and close on both exchanges
        self.assertIn('binance_open', edge.fees_breakdown)
        self.assertIn('binance_close', edge.fees_breakdown)
        self.assertIn('bybit_open', edge.fees_breakdown)
        self.assertIn('bybit_close', edge.fees_breakdown)

        # Total fees should be sum of all fees
        total_fees = sum(edge.fees_breakdown.values())
        self.assertEqual(edge.trading_fees_total, total_fees)

    def test_edge_margin_and_ratio(self):
        """Test edge margin and ratio calculations."""
        edge = self.calculator.calculate_edge(
            trading_pair="BTC-USDT",
            exchange_long="binance",
            exchange_short="bybit",
            funding_rate_long=Decimal("0.0001"),
            funding_rate_short=Decimal("0.001"),  # Large differential
            notional_amount=Decimal("10000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'bybit': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'BTC': Decimal("0.0001"), 'USDT': Decimal("0.00005")},
            slippage_estimates={'binance': Decimal("0.0003"), 'bybit': Decimal("0.0003")}
        )

        # Edge margin = total_edge - min_edge_required
        expected_margin = edge.total_edge - edge.min_edge_required
        self.assertEqual(edge.edge_margin, expected_margin)

        # Edge ratio = total_edge / min_edge_required
        if edge.min_edge_required > 0:
            expected_ratio = edge.total_edge / edge.min_edge_required
            self.assertEqual(edge.edge_ratio, expected_ratio)


class TestEdgeTracker(unittest.TestCase):
    """Test EdgeTracker functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.tracker = EdgeTracker(max_history=100)
        self.calculator = EdgeCalculator()

    def test_add_edge_calculation(self):
        """Test adding edge calculations to tracker."""
        edge = self._create_sample_edge(is_profitable=True)

        self.tracker.add_edge_calculation(edge)

        self.assertEqual(self.tracker.total_count, 1)
        self.assertEqual(self.tracker.profitable_count, 1)

    def test_track_multiple_edges(self):
        """Test tracking multiple edge calculations."""
        # Add 5 profitable and 3 unprofitable
        for _ in range(5):
            self.tracker.add_edge_calculation(self._create_sample_edge(True))

        for _ in range(3):
            self.tracker.add_edge_calculation(self._create_sample_edge(False))

        self.assertEqual(self.tracker.total_count, 8)
        self.assertEqual(self.tracker.profitable_count, 5)

    def test_get_recent_profitable(self):
        """Test retrieving recent profitable opportunities."""
        # Add some profitable edges
        for i in range(10):
            edge = self._create_sample_edge(i % 2 == 0)
            self.tracker.add_edge_calculation(edge)

        recent = self.tracker.get_recent_profitable(count=3)

        self.assertEqual(len(recent), 3)
        for edge in recent:
            self.assertTrue(edge.is_profitable)

    def test_profitability_rate(self):
        """Test profitability rate calculation."""
        # Add edges with known profitability
        for _ in range(7):
            self.tracker.add_edge_calculation(self._create_sample_edge(True))

        for _ in range(3):
            self.tracker.add_edge_calculation(self._create_sample_edge(False))

        # Rate should be 7/10 = 0.7
        rate = self.tracker.get_profitability_rate(lookback_hours=24)
        self.assertAlmostEqual(rate, 0.7, places=2)

    def test_max_history_limit(self):
        """Test that history respects max_history limit."""
        tracker = EdgeTracker(max_history=10)

        # Add 20 edges
        for _ in range(20):
            tracker.add_edge_calculation(self._create_sample_edge(True))

        # Should only keep last 10
        self.assertEqual(len(tracker.edge_history), 10)

    def test_average_edge_components(self):
        """Test calculating average edge components."""
        # Add multiple edges
        for _ in range(5):
            self.tracker.add_edge_calculation(self._create_sample_edge(True))

        averages = self.tracker.get_average_edge_components()

        # Should have all major components
        self.assertIn('expected_funding', averages)
        self.assertIn('trading_fees', averages)
        self.assertIn('borrow_costs', averages)
        self.assertIn('slippage_buffer', averages)
        self.assertIn('total_edge', averages)

        # All averages should be Decimal
        for value in averages.values():
            self.assertIsInstance(value, Decimal)

    def _create_sample_edge(self, is_profitable: bool) -> EdgeDecomposition:
        """Helper to create a sample edge for testing."""
        funding_rate_diff = Decimal("0.001") if is_profitable else Decimal("-0.001")

        edge = self.calculator.calculate_edge(
            trading_pair="BTC-USDT",
            exchange_long="binance",
            exchange_short="bybit",
            funding_rate_long=Decimal("0.0001"),
            funding_rate_short=Decimal("0.0001") + funding_rate_diff,
            notional_amount=Decimal("10000"),
            fees_config={
                'binance': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")},
                'bybit': {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}
            },
            borrow_rates={'BTC': Decimal("0.0001"), 'USDT': Decimal("0.00005")},
            slippage_estimates={'binance': Decimal("0.0003"), 'bybit': Decimal("0.0003")},
            timestamp=time.time()
        )

        return edge


if __name__ == '__main__':
    unittest.main()
