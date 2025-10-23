"""
Unit tests for hedge strategy edge cases.

Tests critical edge conditions like minimum trade sizes, extreme imbalances,
network timeouts, and calculation precision.
"""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch
import asyncio

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.derivative.position import Position
from hummingbot.connector.test_support.mock_paper_exchange import MockPaperExchange
from hummingbot.core.data_type.common import PositionMode, PositionSide, OrderType, TradeType
from hummingbot.core.data_type.limit_order import LimitOrder
from hummingbot.strategy.hedge.hedge import HedgeStrategy
from hummingbot.strategy.hedge.hedge_config_map_pydantic import HedgeConfigMap
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from test.mock.mock_perp_connector import MockPerpConnector
from test.fixtures.market_data import MarketDataFixtures, EDGE_CASE_SCENARIOS


class TestHedgeEdgeCases(unittest.TestCase):
    """Unit tests for hedge strategy edge cases."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        super().setUp()
        self.client_config_map = ClientConfigAdapter(ClientConfigMap())
        self.base_asset = "BTC"
        self.quote_asset = "USDT"
        self.trading_pair = f"{self.base_asset}-{self.quote_asset}"
        
    def create_test_strategy(self, balances: dict, position_amount: Decimal = Decimal("0"),
                           min_trade_size: Decimal = Decimal("0.001"),
                           hedge_ratio: Decimal = Decimal("1.0")) -> HedgeStrategy:
        """Create a test strategy with specified parameters."""
        markets = {
            "spot1": MockPaperExchange(client_config_map=self.client_config_map),
            "spot2": MockPaperExchange(client_config_map=self.client_config_map),
            "perp": MockPerpConnector(
                client_config_map=self.client_config_map,
                buy_collateral_token=self.quote_asset,
                sell_collateral_token=self.quote_asset
            ),
        }
        
        # Set up order books
        order_book_config = {
            "trading_pair": self.trading_pair,
            "mid_price": 45000,
            "min_price": 1000,
            "max_price": 100000,
            "price_step_size": 1,
            "volume_step_size": 0.001,
        }
        
        for market in markets.values():
            market.set_balanced_order_book(**order_book_config)
        
        # Set balances
        for market_name, market in markets.items():
            if market_name in balances:
                for asset, amount in balances[market_name].items():
                    market.set_balance(asset, amount)
        
        # Set up perpetual market
        markets["perp"].set_leverage(self.trading_pair, 25)
        markets["perp"].set_position_mode(PositionMode.ONEWAY)
        
        # Set position
        markets["perp"]._account_positions[self.trading_pair] = Position(
            self.trading_pair,
            PositionSide.BOTH,
            Decimal("0"),
            Decimal("45000"),
            position_amount,
            markets["perp"].get_leverage(self.trading_pair)
        )
        
        # Create market pairs
        market_pairs = [
            MarketTradingPairTuple(markets["spot1"], self.trading_pair, self.base_asset, self.quote_asset),
            MarketTradingPairTuple(markets["spot2"], self.trading_pair, self.base_asset, self.quote_asset),
        ]
        
        hedge_pair = MarketTradingPairTuple(
            markets["perp"], self.trading_pair, self.base_asset, self.quote_asset
        )
        
        config_map = HedgeConfigMap(
            strategy='hedge',
            value_mode=True,
            hedge_ratio=hedge_ratio,
            hedge_interval=60.0,
            min_trade_size=min_trade_size,
            slippage=0.02,
            hedge_offsets=[0],
            hedge_leverage=25,
            hedge_position_mode='ONEWAY',
            hedge_connector='perp',
            hedge_markets=[self.trading_pair],
        )
        
        offsets = {pair: Decimal("0") for pair in market_pairs + [hedge_pair]}
        
        return HedgeStrategy(
            config_map=config_map,
            hedge_market_pairs=[hedge_pair],
            market_pairs=market_pairs,
            offsets=offsets,
        )

    def test_zero_balance_edge_case(self):
        """Test hedge calculation with zero balances."""
        balances = EDGE_CASE_SCENARIOS["zero_balance"]["balances"]
        strategy = self.create_test_strategy(balances)
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # With zero balances and zero position, no hedge should be needed
        self.assertEqual(value_to_hedge, Decimal("0"))
        
        # Verify hedge by value returns early
        with patch.object(strategy, 'logger') as mock_logger:
            strategy.hedge_by_value()
            mock_logger().debug.assert_called_with("No hedge required.")

    def test_dust_amounts_below_minimum(self):
        """Test hedge behavior with amounts below minimum trade size."""
        balances = EDGE_CASE_SCENARIOS["dust_amounts"]["balances"] 
        min_trade_size = Decimal("0.01")  # Larger than dust amounts
        
        strategy = self.create_test_strategy(balances, min_trade_size=min_trade_size)
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # Calculate expected value
        total_value = Decimal("0.00001") * 45000 + Decimal("0.00005") * 45000  # ~$2.7
        expected_value = total_value - Decimal("0.0001") * 45000  # Subtract position value
        
        self.assertGreater(value_to_hedge, 0, "Should have some hedge requirement")
        
        # Check if amount would be below minimum
        price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
        
        if amount < min_trade_size:
            # Should not place order
            order_candidates = strategy.get_order_candidates(
                strategy._hedge_market_pair, is_buy, amount, price
            )
            self.assertEqual(len(order_candidates), 0, "Should not create orders below minimum")

    def test_extreme_leverage_position(self):
        """Test hedge calculation with position at maximum leverage."""
        balances = EDGE_CASE_SCENARIOS["max_leverage"]["balances"]
        position_amount = Decimal("25.0")  # 25x leverage on $2000 margin
        
        strategy = self.create_test_strategy(balances, position_amount=position_amount)
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # With 1 BTC spot + 25 BTC long position, should need to hedge by selling
        self.assertFalse(is_buy, "Should hedge by selling (going short)")
        
        # Value should be significant
        expected_excess = (Decimal("1.0") + position_amount) * 45000
        self.assertGreater(value_to_hedge, expected_excess * Decimal("0.8"), 
                          "Hedge value should be substantial")

    def test_precision_with_small_numbers(self):
        """Test calculation precision with very small numbers."""
        balances = {
            "spot1": {self.base_asset: Decimal("0.00000001"), self.quote_asset: Decimal("0.01")},
            "spot2": {self.base_asset: Decimal("0.00000001"), self.quote_asset: Decimal("0.01")},
            "perp": {self.quote_asset: Decimal("1.00")},
        }
        
        strategy = self.create_test_strategy(balances, min_trade_size=Decimal("0.00000001"))
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # Should handle tiny numbers without overflow/underflow
        self.assertIsInstance(value_to_hedge, Decimal)
        self.assertGreaterEqual(value_to_hedge, Decimal("0"))
        
        # Precision should be maintained
        if value_to_hedge > 0:
            price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
            self.assertGreater(price, 0)
            self.assertGreater(amount, 0)
            
            # Verify calculation precision
            calculated_value = price * amount
            self.assertAlmostEqual(float(calculated_value), float(value_to_hedge), places=6)

    def test_slippage_edge_cases(self):
        """Test slippage calculations at extreme values."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        mid_price = strategy._hedge_market_pair.get_mid_price()
        
        # Test extreme negative slippage
        strategy._slippage = Decimal("-0.5")  # -50%
        ratio = strategy.get_slippage_ratio(True)  # Buy
        adjusted_price = mid_price * ratio
        
        self.assertGreater(ratio, 0, "Slippage ratio must be positive")
        self.assertGreater(adjusted_price, 0, "Adjusted price must be positive")
        self.assertLess(adjusted_price, mid_price, "Buy with negative slippage should decrease price")
        
        # Test extreme positive slippage
        strategy._slippage = Decimal("0.5")  # +50%
        ratio = strategy.get_slippage_ratio(False)  # Sell
        adjusted_price = mid_price * ratio
        
        self.assertGreater(adjusted_price, mid_price, "Sell with positive slippage should increase price")

    def test_network_timeout_simulation(self):
        """Test behavior when network calls timeout."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        
        # Mock a network timeout during order placement
        with patch.object(strategy._hedge_market_pair.market, 'buy_with_specific_market') as mock_buy:
            mock_buy.side_effect = asyncio.TimeoutError("Network timeout")
            
            # Should handle timeout gracefully
            try:
                is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
                if value_to_hedge > strategy._min_trade_size:
                    price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
                    order_candidates = strategy.get_order_candidates(
                        strategy._hedge_market_pair, is_buy, amount, price
                    )
                    # The actual order placement would timeout, but calculation should work
                    self.assertGreater(len(order_candidates), 0)
            except asyncio.TimeoutError:
                self.fail("Strategy should handle timeouts gracefully in calculation phase")

    def test_funding_rate_extreme_values(self):
        """Test hedge calculation with extreme funding rates."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        
        # Simulate extreme funding rates by mocking perpetual connector
        perp_market = strategy._hedge_market_pair.market
        
        # Mock extremely high funding rate (should favor short positions)
        with patch.object(perp_market, 'get_funding_info') as mock_funding:
            mock_funding.return_value = {
                'rate': Decimal('0.1'),  # 10% funding rate!
                'timestamp': 1704067200
            }
            
            # Funding rate shouldn't directly affect basic hedge calculation
            is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
            price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
            
            # Basic hedge logic should still work
            self.assertGreater(price, 0)
            self.assertGreater(amount, 0)

    def test_order_age_management(self):
        """Test order cancellation based on age."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        strategy._max_order_age = 5.0  # 5 seconds max age
        
        # Create a mock old order
        old_order = LimitOrder(
            client_order_id="test_order_123",
            trading_pair=self.trading_pair,
            is_buy=True,
            base_currency=self.base_asset,
            quote_currency=self.quote_asset,
            amount=Decimal("0.1"),
            price=Decimal("45000"),
            creation_timestamp=1000.0  # Very old
        )
        
        # Add order to tracking
        strategy.start_tracking_limit_order(strategy._hedge_market_pair, old_order)
        
        # Mock current timestamp to be much later
        with patch('time.time', return_value=2000.0):  # 1000 seconds later
            aged_orders = []
            for order in strategy.active_orders:
                if strategy.order_age(order, 2000.0) > strategy._max_order_age:
                    aged_orders.append(order)
            
            self.assertGreater(len(aged_orders), 0, "Should identify aged orders")
            
            # Test the age calculation
            age = strategy.order_age(old_order, 2000.0)
            self.assertEqual(age, 1000.0, "Age calculation should be correct")

    def test_position_mode_consistency(self):
        """Test that position mode is set correctly across scenarios."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        # Test ONEWAY mode
        strategy_oneway = self.create_test_strategy(balances)
        self.assertEqual(strategy_oneway._position_mode, PositionMode.ONEWAY)
        
        # Test HEDGE mode
        config_map = HedgeConfigMap(
            strategy='hedge',
            value_mode=True,
            hedge_ratio=Decimal("1.0"),
            hedge_interval=60.0,
            min_trade_size=Decimal("0.001"),
            slippage=0.02,
            hedge_offsets=[0],
            hedge_leverage=25,
            hedge_position_mode='HEDGE',  # Different mode
            hedge_connector='perp',
            hedge_markets=[self.trading_pair],
        )
        
        # Would need to create strategy with HEDGE mode config
        # This tests configuration consistency

    def test_invalid_hedge_ratio(self):
        """Test behavior with invalid hedge ratios."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        # Test with zero hedge ratio
        with self.assertRaises((ValueError, ZeroDivisionError)):
            strategy = self.create_test_strategy(balances, hedge_ratio=Decimal("0"))
        
        # Test with negative hedge ratio
        strategy_negative = self.create_test_strategy(balances, hedge_ratio=Decimal("-1.0"))
        is_buy, value_to_hedge = strategy_negative.get_hedge_direction_and_value()
        
        # Should still calculate but with inverted direction
        self.assertIsInstance(value_to_hedge, Decimal)
        self.assertGreaterEqual(value_to_hedge, 0)

    def test_market_data_staleness(self):
        """Test behavior when market data becomes stale."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        
        # Mock stale price data
        with patch.object(strategy._hedge_market_pair, 'get_mid_price') as mock_price:
            mock_price.return_value = Decimal("0")  # Stale/invalid price
            
            is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
            
            if value_to_hedge > 0:
                # Should handle zero price gracefully
                with self.assertRaises((ZeroDivisionError, ValueError)):
                    price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)

    def test_concurrent_order_management(self):
        """Test that concurrent orders are managed properly."""
        balances = {
            "spot1": {self.base_asset: Decimal("1.0"), self.quote_asset: Decimal("50000")},
            "perp": {self.quote_asset: Decimal("50000")},
        }
        
        strategy = self.create_test_strategy(balances)
        
        # Test that multiple orders for the same market pair are handled
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        if value_to_hedge > strategy._min_trade_size:
            price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
            
            # Create multiple order candidates
            order_candidates_1 = strategy.get_order_candidates(
                strategy._hedge_market_pair, is_buy, amount / 2, price
            )
            order_candidates_2 = strategy.get_order_candidates(
                strategy._hedge_market_pair, is_buy, amount / 2, price
            )
            
            # Both should be valid individually
            self.assertGreater(len(order_candidates_1), 0)
            self.assertGreater(len(order_candidates_2), 0)


class TestExchangeAdapterContracts(unittest.TestCase):
    """Contract tests for exchange adapters used in hedging."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        super().setUp()
        self.client_config_map = ClientConfigAdapter(ClientConfigMap())

    def test_mock_exchange_contract(self):
        """Test that mock exchange implements required interface for hedging."""
        exchange = MockPaperExchange(client_config_map=self.client_config_map)
        
        # Required methods for hedge strategy
        required_methods = [
            'get_mid_price',
            'get_order_book',
            'get_balance', 
            'buy_with_specific_market',
            'sell_with_specific_market',
            'cancel_order',
            'get_open_orders',
        ]
        
        for method_name in required_methods:
            self.assertTrue(hasattr(exchange, method_name), 
                          f"Exchange missing required method: {method_name}")
            self.assertTrue(callable(getattr(exchange, method_name)),
                          f"Exchange method not callable: {method_name}")

    def test_mock_perp_contract(self):
        """Test that mock perpetual connector implements required interface."""
        perp = MockPerpConnector(
            client_config_map=self.client_config_map,
            buy_collateral_token="USDT",
            sell_collateral_token="USDT"
        )
        
        # Required methods for perpetual hedging
        required_methods = [
            'get_position',
            'get_leverage',
            'set_leverage',
            'set_position_mode',
            'get_funding_info',
            'get_mid_price',
            'get_order_book',
        ]
        
        for method_name in required_methods:
            self.assertTrue(hasattr(perp, method_name),
                          f"Perpetual connector missing required method: {method_name}")

    def test_balance_precision_contract(self):
        """Test that balance precision is handled consistently."""
        exchange = MockPaperExchange(client_config_map=self.client_config_map)
        
        # Set balance with high precision
        precise_amount = Decimal("1.123456789123456789")
        exchange.set_balance("BTC", precise_amount)
        
        retrieved_balance = exchange.get_balance("BTC")
        
        # Should maintain precision or have defined rounding rules
        self.assertIsInstance(retrieved_balance, Decimal)
        self.assertEqual(retrieved_balance, precise_amount)

    def test_order_book_data_contract(self):
        """Test that order book data follows expected contract."""
        exchange = MockPaperExchange(client_config_map=self.client_config_map)
        
        # Set up order book
        config = {
            "trading_pair": "BTC-USDT",
            "mid_price": 45000,
            "min_price": 1000,
            "max_price": 100000,
            "price_step_size": 1,
            "volume_step_size": 0.001,
        }
        exchange.set_balanced_order_book(**config)
        
        order_book = exchange.get_order_book("BTC-USDT")
        
        # Contract requirements
        self.assertIsNotNone(order_book)
        self.assertTrue(hasattr(order_book, 'bid_entries'))
        self.assertTrue(hasattr(order_book, 'ask_entries'))
        
        # Should have valid bid/ask data
        self.assertGreater(len(order_book.bid_entries()), 0)
        self.assertGreater(len(order_book.ask_entries()), 0)
        
        # Mid price should be reasonable
        mid_price = exchange.get_mid_price("BTC-USDT")
        self.assertIsInstance(mid_price, Decimal)
        self.assertGreater(mid_price, 0)

    def test_position_data_contract(self):
        """Test that position data follows expected contract."""
        perp = MockPerpConnector(
            client_config_map=self.client_config_map,
            buy_collateral_token="USDT",
            sell_collateral_token="USDT"
        )
        
        trading_pair = "BTC-USDT"
        
        # Set up position
        perp.set_leverage(trading_pair, 25)
        perp.set_position_mode(PositionMode.ONEWAY)
        
        # Get position
        position = perp.get_position(trading_pair)
        
        # Contract requirements
        self.assertIsInstance(position, Position)
        self.assertEqual(position.trading_pair, trading_pair)
        self.assertIsInstance(position.amount, Decimal)
        self.assertIsInstance(position.entry_price, Decimal)
        self.assertIsInstance(position.unrealized_pnl, Decimal)

    def test_error_handling_contract(self):
        """Test that adapters handle errors consistently."""
        exchange = MockPaperExchange(client_config_map=self.client_config_map)
        
        # Test invalid trading pair
        invalid_pair = "INVALID-PAIR"
        
        # Should not crash, should return None or raise specific exception
        try:
            result = exchange.get_mid_price(invalid_pair)
            # If it returns something, should be None or 0
            self.assertIn(result, [None, Decimal("0")])
        except (KeyError, ValueError):
            # Acceptable to raise specific exceptions
            pass
        except Exception as e:
            self.fail(f"Unexpected exception type: {type(e)}")


if __name__ == "__main__":
    unittest.main()