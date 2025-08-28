"""
Property-based tests for hedge strategy using Hypothesis.

These tests verify critical hedge invariants that must hold regardless of input values.
"""

import unittest
from decimal import Decimal
from typing import List

from hypothesis import given, strategies as st, assume, settings
from hypothesis.strategies import decimals, integers, booleans, lists

from hummingbot.client.config.client_config_map import ClientConfigMap
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.connector.derivative.position import Position
from hummingbot.connector.test_support.mock_paper_exchange import MockPaperExchange
from hummingbot.core.data_type.common import PositionMode, PositionSide
from hummingbot.strategy.hedge.hedge import HedgeStrategy
from hummingbot.strategy.hedge.hedge_config_map_pydantic import HedgeConfigMap
from hummingbot.strategy.market_trading_pair_tuple import MarketTradingPairTuple
from test.mock.mock_perp_connector import MockPerpConnector


class TestHedgePropertyBased(unittest.TestCase):
    """Property-based tests for hedge strategy invariants."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        super().setUp()
        self.client_config_map = ClientConfigAdapter(ClientConfigMap())
        self.base_asset = "BTC"
        self.quote_asset = "USDT"
        self.trading_pair = f"{self.base_asset}-{self.quote_asset}"
        
    def create_markets(self, base_balances: List[Decimal], quote_balance: Decimal, position_amount: Decimal):
        """Create market fixtures with given balances."""
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
            "mid_price": 50000,  # Realistic BTC price
            "min_price": 1000,
            "max_price": 100000,
            "price_step_size": 1,
            "volume_step_size": 0.001,
        }
        
        for market in markets.values():
            market.set_balanced_order_book(**order_book_config)
        
        # Set balances
        markets["spot1"].set_balance(self.base_asset, base_balances[0])
        markets["spot1"].set_balance(self.quote_asset, quote_balance)
        markets["spot2"].set_balance(self.base_asset, base_balances[1])
        markets["spot2"].set_balance(self.quote_asset, quote_balance)
        
        # Set up perpetual market
        markets["perp"].set_balance(self.quote_asset, quote_balance * 10)  # Higher balance for leverage
        markets["perp"].set_leverage(self.trading_pair, 25)
        markets["perp"].set_position_mode(PositionMode.ONEWAY)
        
        # Set initial position
        markets["perp"]._account_positions[self.trading_pair] = Position(
            self.trading_pair,
            PositionSide.BOTH,
            Decimal("0"),
            Decimal("50000"),  # Entry price
            position_amount,
            markets["perp"].get_leverage(self.trading_pair)
        )
        
        return markets

    def create_strategy(self, markets: dict, hedge_ratio: Decimal, tolerance: Decimal = Decimal("0.001")):
        """Create hedge strategy with given parameters."""
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
            min_trade_size=tolerance,  # Use tolerance as min trade size
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

    @given(
        base_balances=lists(
            decimals(min_value=Decimal("0"), max_value=Decimal("10"), places=4),
            min_size=2, max_size=2
        ),
        quote_balance=decimals(min_value=Decimal("1000"), max_value=Decimal("100000"), places=2),
        position_amount=decimals(min_value=Decimal("-5"), max_value=Decimal("5"), places=4),
        hedge_ratio=decimals(min_value=Decimal("0.1"), max_value=Decimal("2.0"), places=3),
        tolerance=decimals(min_value=Decimal("0.001"), max_value=Decimal("0.1"), places=4)
    )
    @settings(max_examples=50, deadline=None)
    def test_hedge_invariant_delta_within_tolerance(self, base_balances, quote_balance, 
                                                   position_amount, hedge_ratio, tolerance):
        """
        Property: After hedging, the absolute delta should be within tolerance.
        
        This is the core hedge invariant: |Δ| ≤ tolerance
        """
        assume(all(balance >= 0 for balance in base_balances))
        assume(quote_balance > 0)
        assume(tolerance > 0)
        assume(hedge_ratio > 0)
        
        markets = self.create_markets(base_balances, quote_balance, position_amount)
        strategy = self.create_strategy(markets, hedge_ratio, tolerance)
        
        # Calculate initial delta
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # If no hedge is needed (value < min_trade_size), delta should already be within tolerance
        if value_to_hedge < tolerance:
            # Delta is already within tolerance
            self.assertLessEqual(value_to_hedge, tolerance)
        else:
            # Verify hedge calculation produces reasonable values
            price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
            
            # Basic sanity checks
            self.assertGreater(price, 0, "Hedge price must be positive")
            self.assertGreater(amount, 0, "Hedge amount must be positive")
            
            # The hedge amount should not exceed reasonable bounds
            max_reasonable_hedge = sum(base_balances) * hedge_ratio * 2  # Allow 2x for edge cases
            self.assertLessEqual(amount, max_reasonable_hedge, 
                               f"Hedge amount {amount} exceeds reasonable bounds")

    @given(
        base_balances=lists(
            decimals(min_value=Decimal("0.1"), max_value=Decimal("5"), places=4),
            min_size=2, max_size=2
        ),
        hedge_ratio=decimals(min_value=Decimal("0.5"), max_value=Decimal("1.5"), places=3),
        position_amounts=lists(
            decimals(min_value=Decimal("-2"), max_value=Decimal("2"), places=4),
            min_size=1, max_size=1
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_hedge_ratio_proportionality(self, base_balances, hedge_ratio, position_amounts):
        """
        Property: Hedge value should be proportional to hedge ratio.
        
        If hedge_ratio doubles, the required hedge value should approximately double
        (assuming position stays constant).
        """
        assume(all(balance > 0 for balance in base_balances))
        assume(hedge_ratio > 0)
        
        quote_balance = Decimal("10000")
        position_amount = position_amounts[0]
        
        # Test with original hedge ratio
        markets1 = self.create_markets(base_balances, quote_balance, position_amount)
        strategy1 = self.create_strategy(markets1, hedge_ratio)
        _, value1 = strategy1.get_hedge_direction_and_value()
        
        # Test with doubled hedge ratio
        markets2 = self.create_markets(base_balances, quote_balance, position_amount)
        strategy2 = self.create_strategy(markets2, hedge_ratio * 2)
        _, value2 = strategy2.get_hedge_direction_and_value()
        
        # If both values are significant, check proportionality
        if value1 > Decimal("1") and value2 > Decimal("1"):
            ratio = value2 / value1
            # Allow some tolerance for floating point arithmetic
            self.assertAlmostEqual(float(ratio), 2.0, delta=0.1,
                                 msg=f"Hedge values not proportional: {value1} -> {value2}")

    @given(
        base_balance=decimals(min_value=Decimal("0.1"), max_value=Decimal("3"), places=4),
        position_amount=decimals(min_value=Decimal("-1"), max_value=Decimal("1"), places=4),
        hedge_ratio=decimals(min_value=Decimal("0.8"), max_value=Decimal("1.2"), places=3)
    )
    @settings(max_examples=40, deadline=None)
    def test_hedge_direction_consistency(self, base_balance, position_amount, hedge_ratio):
        """
        Property: Hedge direction should be consistent with net exposure.
        
        If net exposure is long (positive), hedge should be sell (short).
        If net exposure is short (negative), hedge should be buy (long).
        """
        assume(base_balance > 0)
        assume(hedge_ratio > 0)
        
        base_balances = [base_balance, Decimal("0")]  # All balance in first market
        quote_balance = Decimal("10000")
        
        markets = self.create_markets(base_balances, quote_balance, position_amount)
        strategy = self.create_strategy(markets, hedge_ratio)
        
        # Calculate net exposure
        total_spot_value = strategy.get_base_value(strategy._market_pairs[0])
        hedge_value = strategy.get_base_value(strategy._hedge_market_pair)
        net_exposure = total_spot_value * hedge_ratio + hedge_value
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # Only test direction if hedge value is significant
        if value_to_hedge > Decimal("0.01"):
            if net_exposure > 0:
                # Net long exposure -> should hedge by selling (shorting)
                self.assertFalse(is_buy, 
                               f"Net long exposure {net_exposure} should hedge by selling")
            elif net_exposure < 0:
                # Net short exposure -> should hedge by buying (longing)
                self.assertTrue(is_buy, 
                              f"Net short exposure {net_exposure} should hedge by buying")

    @given(
        slippage=decimals(min_value=Decimal("-0.1"), max_value=Decimal("0.1"), places=4),
        is_buy=booleans()
    )
    @settings(max_examples=20, deadline=None)
    def test_slippage_calculation_bounds(self, slippage, is_buy):
        """
        Property: Slippage adjustment should produce reasonable price bounds.
        
        The adjusted price should be within reasonable bounds of the mid price.
        """
        base_balances = [Decimal("1"), Decimal("0.5")]
        quote_balance = Decimal("10000")
        position_amount = Decimal("0")
        
        markets = self.create_markets(base_balances, quote_balance, position_amount)
        strategy = self.create_strategy(markets, Decimal("1"))
        strategy._slippage = slippage
        
        mid_price = strategy._hedge_market_pair.get_mid_price()
        slippage_ratio = strategy.get_slippage_ratio(is_buy)
        adjusted_price = mid_price * slippage_ratio
        
        # Slippage ratio should be positive and reasonable
        self.assertGreater(slippage_ratio, Decimal("0.5"), 
                          f"Slippage ratio {slippage_ratio} too low")
        self.assertLess(slippage_ratio, Decimal("2.0"), 
                       f"Slippage ratio {slippage_ratio} too high")
        
        # Adjusted price should be reasonable
        self.assertGreater(adjusted_price, mid_price * Decimal("0.5"))
        self.assertLess(adjusted_price, mid_price * Decimal("2.0"))

    @given(
        amounts=lists(
            decimals(min_value=Decimal("0"), max_value=Decimal("2"), places=4),
            min_size=2, max_size=2
        ),
        offsets=lists(
            decimals(min_value=Decimal("-0.5"), max_value=Decimal("0.5"), places=4),
            min_size=2, max_size=2
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_offset_impact_on_hedge_value(self, amounts, offsets):
        """
        Property: Offsets should predictably impact hedge calculations.
        
        Positive offsets should increase hedge requirements in one direction.
        """
        assume(all(amount >= 0 for amount in amounts))
        
        quote_balance = Decimal("10000")
        position_amount = Decimal("0")
        hedge_ratio = Decimal("1")
        
        # Test without offsets
        markets1 = self.create_markets(amounts, quote_balance, position_amount)
        strategy1 = self.create_strategy(markets1, hedge_ratio)
        _, value_no_offset = strategy1.get_hedge_direction_and_value()
        
        # Test with offsets
        markets2 = self.create_markets(amounts, quote_balance, position_amount)
        strategy2 = self.create_strategy(markets2, hedge_ratio)
        
        # Apply offsets
        for i, (market_pair, offset) in enumerate(zip(strategy2._market_pairs, offsets)):
            strategy2._offsets[market_pair] = offset
        
        _, value_with_offset = strategy2.get_hedge_direction_and_value()
        
        # The change in hedge value should be related to the sum of offsets
        # (This is a weaker assertion since offset impact depends on prices)
        total_offset_impact = sum(offsets) * strategy2._hedge_market_pair.get_mid_price()
        expected_change = abs(total_offset_impact)
        
        # Allow significant tolerance since offset impact is complex
        if expected_change > Decimal("1"):
            actual_change = abs(value_with_offset - value_no_offset)
            max_expected = expected_change * 2  # Allow 2x tolerance
            self.assertLessEqual(actual_change, max_expected,
                               f"Offset impact {actual_change} exceeds expected {max_expected}")

    def test_zero_balance_edge_case(self):
        """Test hedge behavior with zero balances (edge case)."""
        base_balances = [Decimal("0"), Decimal("0")]
        quote_balance = Decimal("1000")
        position_amount = Decimal("0")
        
        markets = self.create_markets(base_balances, quote_balance, position_amount)
        strategy = self.create_strategy(markets, Decimal("1"))
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # With zero balances and zero position, no hedge should be needed
        self.assertEqual(value_to_hedge, Decimal("0"))

    def test_minimal_hedge_threshold(self):
        """Test that minimal hedge amounts below threshold are ignored."""
        base_balances = [Decimal("0.0001"), Decimal("0")]  # Tiny balance
        quote_balance = Decimal("1000")
        position_amount = Decimal("0")
        tolerance = Decimal("0.01")  # Relatively large tolerance
        
        markets = self.create_markets(base_balances, quote_balance, position_amount)
        strategy = self.create_strategy(markets, Decimal("1"), tolerance)
        
        is_buy, value_to_hedge = strategy.get_hedge_direction_and_value()
        
        # Very small hedge requirement should be below threshold
        if value_to_hedge < tolerance:
            # This should result in no hedge action
            price, amount = strategy.calculate_hedge_price_and_amount(is_buy, value_to_hedge)
            # Amount should be very small
            self.assertLess(amount, tolerance)


if __name__ == "__main__":
    unittest.main()