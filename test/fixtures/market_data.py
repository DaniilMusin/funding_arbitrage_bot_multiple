"""
Test fixtures with real-world market data snapshots and edge cases.

This module provides realistic market data for testing hedge strategies,
including scenarios with high volatility, low liquidity, and network issues.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import pandas as pd


@dataclass
class OrderBookSnapshot:
    """Represents an order book snapshot with bids and asks."""
    timestamp: datetime
    exchange: str
    trading_pair: str
    bids: List[List[Decimal]]  # [[price, quantity], ...]
    asks: List[List[Decimal]]  # [[price, quantity], ...]
    mid_price: Decimal
    spread_bps: Decimal  # Spread in basis points
    
    @property
    def best_bid(self) -> Decimal:
        return self.bids[0][0] if self.bids else Decimal("0")
    
    @property 
    def best_ask(self) -> Decimal:
        return self.asks[0][0] if self.asks else Decimal("0")


@dataclass
class FundingSnapshot:
    """Represents funding rate data for perpetual markets."""
    timestamp: datetime
    exchange: str
    trading_pair: str
    funding_rate: Decimal  # 8-hour funding rate
    predicted_funding_rate: Optional[Decimal]
    mark_price: Decimal
    index_price: Decimal
    open_interest: Decimal


@dataclass
class MarketCondition:
    """Represents overall market conditions."""
    condition_name: str
    description: str
    btc_volatility_24h: Decimal  # Percentage
    market_trend: str  # "bull", "bear", "sideways", "crash"
    network_congestion: bool
    high_gas_fees: bool


class MarketDataFixtures:
    """Factory for creating realistic market data fixtures."""
    
    @staticmethod
    def create_normal_market_btc_usdt() -> Dict[str, Any]:
        """Create normal market conditions for BTC-USDT."""
        timestamp = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        
        spot_books = {
            "binance": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="binance",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("42500.50"), Decimal("0.25")],
                    [Decimal("42500.00"), Decimal("0.50")],
                    [Decimal("42499.50"), Decimal("1.00")],
                    [Decimal("42499.00"), Decimal("2.50")],
                    [Decimal("42498.50"), Decimal("5.00")],
                ],
                asks=[
                    [Decimal("42501.50"), Decimal("0.25")],
                    [Decimal("42502.00"), Decimal("0.50")],
                    [Decimal("42502.50"), Decimal("1.00")],
                    [Decimal("42503.00"), Decimal("2.50")],
                    [Decimal("42503.50"), Decimal("5.00")],
                ],
                mid_price=Decimal("42501.00"),
                spread_bps=Decimal("2.35")  # $1 spread on $42501 = 2.35 bps
            ),
            "coinbase": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="coinbase",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("42499.90"), Decimal("0.15")],
                    [Decimal("42499.40"), Decimal("0.30")],
                    [Decimal("42498.90"), Decimal("0.80")],
                    [Decimal("42498.40"), Decimal("2.00")],
                    [Decimal("42497.90"), Decimal("3.50")],
                ],
                asks=[
                    [Decimal("42502.10"), Decimal("0.15")],
                    [Decimal("42502.60"), Decimal("0.30")],
                    [Decimal("42503.10"), Decimal("0.80")],
                    [Decimal("42503.60"), Decimal("2.00")],
                    [Decimal("42504.10"), Decimal("3.50")],
                ],
                mid_price=Decimal("42501.00"),
                spread_bps=Decimal("5.18")  # $2.2 spread = 5.18 bps
            )
        }
        
        perp_book = OrderBookSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            bids=[
                [Decimal("42500.8"), Decimal("5.50")],
                [Decimal("42500.3"), Decimal("10.00")],
                [Decimal("42499.8"), Decimal("25.00")],
                [Decimal("42499.3"), Decimal("50.00")],
                [Decimal("42498.8"), Decimal("100.00")],
            ],
            asks=[
                [Decimal("42501.2"), Decimal("5.50")],
                [Decimal("42501.7"), Decimal("10.00")],
                [Decimal("42502.2"), Decimal("25.00")],
                [Decimal("42502.7"), Decimal("50.00")],
                [Decimal("42503.2"), Decimal("100.00")],
            ],
            mid_price=Decimal("42501.00"),
            spread_bps=Decimal("0.94")  # Tighter spread for perps
        )
        
        funding = FundingSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            funding_rate=Decimal("0.0001"),  # 0.01% = 1bp
            predicted_funding_rate=Decimal("0.0002"),
            mark_price=Decimal("42501.00"),
            index_price=Decimal("42500.85"),
            open_interest=Decimal("15420.5")
        )
        
        condition = MarketCondition(
            condition_name="normal_market",
            description="Normal trading conditions with typical spreads",
            btc_volatility_24h=Decimal("2.5"),
            market_trend="sideways",
            network_congestion=False,
            high_gas_fees=False
        )
        
        return {
            "spot_books": spot_books,
            "perp_book": perp_book,
            "funding": funding,
            "condition": condition,
            "balances": {
                "binance": {"BTC": Decimal("1.5"), "USDT": Decimal("25000")},
                "coinbase": {"BTC": Decimal("0.8"), "USDT": Decimal("15000")},
                "binance_perpetual": {"USDT": Decimal("100000")},
            },
            "positions": {
                "binance_perpetual": {
                    "BTC-USDT": {
                        "amount": Decimal("-2.1"),  # Short position
                        "entry_price": Decimal("42800"),
                        "unrealized_pnl": Decimal("629.79"),  # Positive PnL from short
                    }
                }
            }
        }

    @staticmethod
    def create_high_volatility_crash() -> Dict[str, Any]:
        """Create high volatility market crash scenario."""
        timestamp = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        # Wide spreads during crash
        spot_books = {
            "binance": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="binance",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("38500.00"), Decimal("0.05")],  # Thin liquidity
                    [Decimal("38450.00"), Decimal("0.10")],
                    [Decimal("38400.00"), Decimal("0.25")],
                    [Decimal("38350.00"), Decimal("0.50")],
                    [Decimal("38300.00"), Decimal("1.00")],
                ],
                asks=[
                    [Decimal("38650.00"), Decimal("0.05")],
                    [Decimal("38700.00"), Decimal("0.10")],
                    [Decimal("38750.00"), Decimal("0.25")],
                    [Decimal("38800.00"), Decimal("0.50")],
                    [Decimal("38850.00"), Decimal("1.00")],
                ],
                mid_price=Decimal("38575.00"),
                spread_bps=Decimal("389")  # ~$150 spread = 389 bps
            ),
            "coinbase": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="coinbase",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("38450.00"), Decimal("0.03")],
                    [Decimal("38400.00"), Decimal("0.08")],
                    [Decimal("38350.00"), Decimal("0.15")],
                    [Decimal("38300.00"), Decimal("0.30")],
                    [Decimal("38250.00"), Decimal("0.60")],
                ],
                asks=[
                    [Decimal("38750.00"), Decimal("0.03")],
                    [Decimal("38800.00"), Decimal("0.08")],
                    [Decimal("38850.00"), Decimal("0.15")],
                    [Decimal("38900.00"), Decimal("0.30")],
                    [Decimal("38950.00"), Decimal("0.60")],
                ],
                mid_price=Decimal("38600.00"),
                spread_bps=Decimal("777")  # Even wider spread
            )
        }
        
        perp_book = OrderBookSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            bids=[
                [Decimal("38520.0"), Decimal("2.0")],
                [Decimal("38500.0"), Decimal("5.0")],
                [Decimal("38480.0"), Decimal("10.0")],
                [Decimal("38460.0"), Decimal("20.0")],
                [Decimal("38440.0"), Decimal("50.0")],
            ],
            asks=[
                [Decimal("38580.0"), Decimal("2.0")],
                [Decimal("38600.0"), Decimal("5.0")],
                [Decimal("38620.0"), Decimal("10.0")],
                [Decimal("38640.0"), Decimal("20.0")],
                [Decimal("38660.0"), Decimal("50.0")],
            ],
            mid_price=Decimal("38550.00"),
            spread_bps=Decimal("156")  # $60 spread
        )
        
        funding = FundingSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual", 
            trading_pair="BTC-USDT",
            funding_rate=Decimal("-0.0150"),  # Negative funding during crash
            predicted_funding_rate=Decimal("-0.0200"),
            mark_price=Decimal("38550.00"),
            index_price=Decimal("38525.00"),
            open_interest=Decimal("12850.2")  # Reduced OI from liquidations
        )
        
        condition = MarketCondition(
            condition_name="crash_scenario",
            description="Market crash with high volatility and wide spreads",
            btc_volatility_24h=Decimal("15.8"),
            market_trend="crash",
            network_congestion=True,
            high_gas_fees=True
        )
        
        return {
            "spot_books": spot_books,
            "perp_book": perp_book,
            "funding": funding,
            "condition": condition,
            "balances": {
                "binance": {"BTC": Decimal("1.2"), "USDT": Decimal("45000")},  # More cash during crash
                "coinbase": {"BTC": Decimal("0.3"), "USDT": Decimal("25000")},
                "binance_perpetual": {"USDT": Decimal("80000")},  # Reduced margin
            },
            "positions": {
                "binance_perpetual": {
                    "BTC-USDT": {
                        "amount": Decimal("0.5"),  # Small long position underwater
                        "entry_price": Decimal("42000"),
                        "unrealized_pnl": Decimal("-1725.00"),  # Large loss
                    }
                }
            }
        }

    @staticmethod
    def create_low_liquidity_altcoin() -> Dict[str, Any]:
        """Create low liquidity altcoin scenario with timing issues."""
        timestamp = datetime(2024, 1, 15, 16, 45, 0, tzinfo=timezone.utc)
        
        # Simulating ETH-USDT with timing/delta issues
        spot_books = {
            "binance": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="binance", 
                trading_pair="ETH-USDT",
                bids=[
                    [Decimal("2545.50"), Decimal("0.8")],
                    [Decimal("2545.00"), Decimal("2.5")],
                    [Decimal("2544.50"), Decimal("5.0")],
                    [Decimal("2544.00"), Decimal("10.0")],
                    [Decimal("2543.50"), Decimal("25.0")],
                ],
                asks=[
                    [Decimal("2546.50"), Decimal("0.8")],
                    [Decimal("2547.00"), Decimal("2.5")],
                    [Decimal("2547.50"), Decimal("5.0")],
                    [Decimal("2548.00"), Decimal("10.0")],
                    [Decimal("2548.50"), Decimal("25.0")],
                ],
                mid_price=Decimal("2546.00"),
                spread_bps=Decimal("39")  # $1 spread
            ),
            "coinbase": OrderBookSnapshot(
                timestamp=timestamp + pd.Timedelta(seconds=2),  # Timing delta!
                exchange="coinbase",
                trading_pair="ETH-USDT", 
                bids=[
                    [Decimal("2544.80"), Decimal("0.5")],  # Stale prices
                    [Decimal("2544.30"), Decimal("1.2")],
                    [Decimal("2543.80"), Decimal("3.0")],
                    [Decimal("2543.30"), Decimal("8.0")],
                    [Decimal("2542.80"), Decimal("15.0")],
                ],
                asks=[
                    [Decimal("2547.20"), Decimal("0.5")],
                    [Decimal("2547.70"), Decimal("1.2")],
                    [Decimal("2548.20"), Decimal("3.0")],
                    [Decimal("2548.70"), Decimal("8.0")],
                    [Decimal("2549.20"), Decimal("15.0")],
                ],
                mid_price=Decimal("2546.00"),  # Same mid but different book
                spread_bps=Decimal("94")  # Wider spread
            )
        }
        
        perp_book = OrderBookSnapshot(
            timestamp=timestamp - pd.Timedelta(seconds=1),  # Another timing delta
            exchange="binance_perpetual",
            trading_pair="ETH-USDT",
            bids=[
                [Decimal("2545.8"), Decimal("15.0")],
                [Decimal("2545.3"), Decimal("30.0")],
                [Decimal("2544.8"), Decimal("75.0")],
                [Decimal("2544.3"), Decimal("150.0")],
                [Decimal("2543.8"), Decimal("300.0")],
            ],
            asks=[
                [Decimal("2546.2"), Decimal("15.0")],
                [Decimal("2546.7"), Decimal("30.0")],
                [Decimal("2547.2"), Decimal("75.0")],
                [Decimal("2547.7"), Decimal("150.0")],
                [Decimal("2548.2"), Decimal("300.0")],
            ],
            mid_price=Decimal("2546.00"),
            spread_bps=Decimal("16")  # Tighter perp spread
        )
        
        funding = FundingSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="ETH-USDT", 
            funding_rate=Decimal("0.0008"),
            predicted_funding_rate=Decimal("0.0012"),
            mark_price=Decimal("2546.00"),
            index_price=Decimal("2545.85"),
            open_interest=Decimal("8520.8")
        )
        
        condition = MarketCondition(
            condition_name="timing_deltas",
            description="Normal market with timing issues between exchanges",
            btc_volatility_24h=Decimal("3.2"),
            market_trend="sideways",
            network_congestion=False,
            high_gas_fees=False
        )
        
        return {
            "spot_books": spot_books,
            "perp_book": perp_book,
            "funding": funding,
            "condition": condition,
            "balances": {
                "binance": {"ETH": Decimal("12.5"), "USDT": Decimal("8000")},
                "coinbase": {"ETH": Decimal("7.8"), "USDT": Decimal("5000")},
                "binance_perpetual": {"USDT": Decimal("50000")},
            },
            "positions": {
                "binance_perpetual": {
                    "ETH-USDT": {
                        "amount": Decimal("-18.2"),  # Moderate short
                        "entry_price": Decimal("2580"),
                        "unrealized_pnl": Decimal("618.36"),  # Small profit
                    }
                }
            }
        }

    @staticmethod
    def create_funding_arbitrage_opportunity() -> Dict[str, Any]:
        """Create scenario with significant funding rate arbitrage opportunity."""
        timestamp = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
        
        # Normal spot books
        spot_books = {
            "binance": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="binance",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("43200.50"), Decimal("0.30")],
                    [Decimal("43200.00"), Decimal("0.75")],
                    [Decimal("43199.50"), Decimal("1.50")],
                    [Decimal("43199.00"), Decimal("3.00")],
                    [Decimal("43198.50"), Decimal("6.00")],
                ],
                asks=[
                    [Decimal("43201.50"), Decimal("0.30")],
                    [Decimal("43202.00"), Decimal("0.75")],
                    [Decimal("43202.50"), Decimal("1.50")],
                    [Decimal("43203.00"), Decimal("3.00")],
                    [Decimal("43203.50"), Decimal("6.00")],
                ],
                mid_price=Decimal("43201.00"),
                spread_bps=Decimal("2.31")
            )
        }
        
        perp_book = OrderBookSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            bids=[
                [Decimal("43200.8"), Decimal("8.0")],
                [Decimal("43200.3"), Decimal("15.0")],
                [Decimal("43199.8"), Decimal("30.0")],
                [Decimal("43199.3"), Decimal("60.0")],
                [Decimal("43198.8"), Decimal("120.0")],
            ],
            asks=[
                [Decimal("43201.2"), Decimal("8.0")],
                [Decimal("43201.7"), Decimal("15.0")],
                [Decimal("43202.2"), Decimal("30.0")],
                [Decimal("43202.7"), Decimal("60.0")],
                [Decimal("43203.2"), Decimal("120.0")],
            ],
            mid_price=Decimal("43201.00"),
            spread_bps=Decimal("0.93")
        )
        
        # High positive funding rate = profitable to be short
        funding = FundingSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            funding_rate=Decimal("0.0075"),  # 0.75% = 75bp (very high!)
            predicted_funding_rate=Decimal("0.0080"),
            mark_price=Decimal("43201.00"),
            index_price=Decimal("43200.75"),
            open_interest=Decimal("18950.4")
        )
        
        condition = MarketCondition(
            condition_name="high_funding",
            description="High funding rate creating arbitrage opportunity",
            btc_volatility_24h=Decimal("4.1"),
            market_trend="bull",
            network_congestion=False,
            high_gas_fees=False
        )
        
        return {
            "spot_books": spot_books,
            "perp_book": perp_book,
            "funding": funding,
            "condition": condition,
            "balances": {
                "binance": {"BTC": Decimal("3.0"), "USDT": Decimal("50000")},
                "binance_perpetual": {"USDT": Decimal("150000")},
            },
            "positions": {
                "binance_perpetual": {
                    "BTC-USDT": {
                        "amount": Decimal("0"),  # No position yet
                        "entry_price": Decimal("0"),
                        "unrealized_pnl": Decimal("0"),
                    }
                }
            }
        }

    @staticmethod
    def create_extreme_imbalance() -> Dict[str, Any]:
        """Create scenario with extreme portfolio imbalance requiring large hedge."""
        timestamp = datetime(2024, 1, 15, 22, 15, 0, tzinfo=timezone.utc)
        
        spot_books = {
            "binance": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="binance",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("41800.00"), Decimal("0.20")],
                    [Decimal("41799.50"), Decimal("0.50")],
                    [Decimal("41799.00"), Decimal("1.00")],
                    [Decimal("41798.50"), Decimal("2.50")],
                    [Decimal("41798.00"), Decimal("5.00")],
                ],
                asks=[
                    [Decimal("41801.00"), Decimal("0.20")],
                    [Decimal("41801.50"), Decimal("0.50")],
                    [Decimal("41802.00"), Decimal("1.00")],
                    [Decimal("41802.50"), Decimal("2.50")],
                    [Decimal("41803.00"), Decimal("5.00")],
                ],
                mid_price=Decimal("41800.50"),
                spread_bps=Decimal("2.39")
            ),
            "coinbase": OrderBookSnapshot(
                timestamp=timestamp,
                exchange="coinbase",
                trading_pair="BTC-USDT",
                bids=[
                    [Decimal("41799.00"), Decimal("0.15")],
                    [Decimal("41798.50"), Decimal("0.35")],
                    [Decimal("41798.00"), Decimal("0.75")],
                    [Decimal("41797.50"), Decimal("1.75")],
                    [Decimal("41797.00"), Decimal("3.50")],
                ],
                asks=[
                    [Decimal("41802.00"), Decimal("0.15")],
                    [Decimal("41802.50"), Decimal("0.35")],
                    [Decimal("41803.00"), Decimal("0.75")],
                    [Decimal("41803.50"), Decimal("1.75")],
                    [Decimal("41804.00"), Decimal("3.50")],
                ],
                mid_price=Decimal("41800.50"),
                spread_bps=Decimal("7.18")
            )
        }
        
        perp_book = OrderBookSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            bids=[
                [Decimal("41800.2"), Decimal("12.0")],
                [Decimal("41799.7"), Decimal("25.0")],
                [Decimal("41799.2"), Decimal("50.0")],
                [Decimal("41798.7"), Decimal("100.0")],
                [Decimal("41798.2"), Decimal("200.0")],
            ],
            asks=[
                [Decimal("41800.8"), Decimal("12.0")],
                [Decimal("41801.3"), Decimal("25.0")],
                [Decimal("41801.8"), Decimal("50.0")],
                [Decimal("41802.3"), Decimal("100.0")],
                [Decimal("41802.8"), Decimal("200.0")],
            ],
            mid_price=Decimal("41800.50"),
            spread_bps=Decimal("1.44")
        )
        
        funding = FundingSnapshot(
            timestamp=timestamp,
            exchange="binance_perpetual",
            trading_pair="BTC-USDT",
            funding_rate=Decimal("0.0003"),
            predicted_funding_rate=Decimal("0.0005"),
            mark_price=Decimal("41800.50"),
            index_price=Decimal("41800.25"),
            open_interest=Decimal("16750.6")
        )
        
        condition = MarketCondition(
            condition_name="extreme_imbalance",
            description="Extreme portfolio imbalance requiring large hedge",
            btc_volatility_24h=Decimal("3.8"),
            market_trend="sideways",
            network_congestion=False,
            high_gas_fees=False
        )
        
        return {
            "spot_books": spot_books,
            "perp_book": perp_book,
            "funding": funding,
            "condition": condition,
            "balances": {
                # Huge imbalance - too much BTC
                "binance": {"BTC": Decimal("25.0"), "USDT": Decimal("10000")},
                "coinbase": {"BTC": Decimal("15.0"), "USDT": Decimal("5000")},
                "binance_perpetual": {"USDT": Decimal("200000")},
            },
            "positions": {
                "binance_perpetual": {
                    "BTC-USDT": {
                        "amount": Decimal("5.0"),  # Already long, making imbalance worse
                        "entry_price": Decimal("40500"),
                        "unrealized_pnl": Decimal("6502.50"),  # Large profit
                    }
                }
            }
        }

    @staticmethod
    def save_fixture_to_file(fixture_data: Dict[str, Any], filename: str) -> None:
        """Save fixture data to JSON file for reuse."""
        
        def decimal_converter(obj):
            if isinstance(obj, Decimal):
                return str(obj)
            elif isinstance(obj, datetime):
                return obj.isoformat()
            elif hasattr(obj, '__dict__'):
                return asdict(obj) if hasattr(obj, '__dataclass_fields__') else obj.__dict__
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        with open(filename, 'w') as f:
            json.dump(fixture_data, f, default=decimal_converter, indent=2)

    @staticmethod 
    def load_fixture_from_file(filename: str) -> Dict[str, Any]:
        """Load fixture data from JSON file."""
        with open(filename, 'r') as f:
            return json.load(f)


# Edge case scenarios for specific testing
EDGE_CASE_SCENARIOS = {
    "zero_balance": {
        "description": "All balances are zero",
        "balances": {
            "binance": {"BTC": Decimal("0"), "USDT": Decimal("0")},
            "coinbase": {"BTC": Decimal("0"), "USDT": Decimal("0")},
            "binance_perpetual": {"USDT": Decimal("1000")},  # Minimal margin
        },
        "positions": {
            "binance_perpetual": {"BTC-USDT": {"amount": Decimal("0"), "entry_price": Decimal("0"), "unrealized_pnl": Decimal("0")}}
        }
    },
    
    "dust_amounts": {
        "description": "Very small amounts below typical minimum trade sizes",
        "balances": {
            "binance": {"BTC": Decimal("0.00001"), "USDT": Decimal("0.50")},
            "coinbase": {"BTC": Decimal("0.00005"), "USDT": Decimal("1.25")},
            "binance_perpetual": {"USDT": Decimal("10")},
        },
        "positions": {
            "binance_perpetual": {"BTC-USDT": {"amount": Decimal("0.0001"), "entry_price": Decimal("45000"), "unrealized_pnl": Decimal("-0.45")}}
        }
    },
    
    "max_leverage": {
        "description": "Position at maximum leverage",
        "balances": {
            "binance": {"BTC": Decimal("1.0"), "USDT": Decimal("50000")},
            "binance_perpetual": {"USDT": Decimal("2000")},  # Small margin
        },
        "positions": {
            "binance_perpetual": {"BTC-USDT": {"amount": Decimal("25.0"), "entry_price": Decimal("40000"), "unrealized_pnl": Decimal("0")}}
        }
    }
}


if __name__ == "__main__":
    # Generate and save all fixtures
    fixtures = MarketDataFixtures()
    
    scenarios = [
        ("normal_market", fixtures.create_normal_market_btc_usdt()),
        ("high_volatility_crash", fixtures.create_high_volatility_crash()),
        ("low_liquidity_timing", fixtures.create_low_liquidity_altcoin()),
        ("funding_arbitrage", fixtures.create_funding_arbitrage_opportunity()),
        ("extreme_imbalance", fixtures.create_extreme_imbalance()),
    ]
    
    for name, data in scenarios:
        fixtures.save_fixture_to_file(data, f"test/fixtures/{name}.json")
        print(f"Saved {name} fixture")
    
    print(f"Generated {len(scenarios)} market data fixtures")