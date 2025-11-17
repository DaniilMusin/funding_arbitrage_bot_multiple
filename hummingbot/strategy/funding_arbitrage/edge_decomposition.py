"""
Edge decomposition system for funding arbitrage strategy.
Calculates and tracks all components that determine entry viability.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, NamedTuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EdgeComponent(Enum):
    """Components that make up the total edge calculation."""
    EXPECTED_FUNDING = "expected_funding"
    TRADING_FEES = "trading_fees"
    BORROW_COST = "borrow_cost"
    SLIPPAGE_BUFFER = "slippage_buffer"
    SETTLEMENT_BUFFER = "settlement_buffer"


@dataclass
class EdgeDecomposition:
    """
    Detailed breakdown of edge calculation for transparency.
    Shows why a position was or wasn't entered.
    """
    trading_pair: str
    exchange_long: str
    exchange_short: str
    timestamp: float
    
    # Core components
    expected_funding_rate: Decimal
    expected_funding_pnl: Decimal
    trading_fees_total: Decimal
    borrow_cost_total: Decimal
    slippage_buffer_total: Decimal
    settlement_buffer: Decimal
    
    # Detailed breakdowns
    fees_breakdown: Dict[str, Decimal]
    borrow_breakdown: Dict[str, Decimal]
    slippage_breakdown: Dict[str, Decimal]
    
    # Position sizing
    notional_amount: Decimal
    leverage_long: Decimal
    leverage_short: Decimal
    
    # Final calculation
    total_edge: Decimal
    min_edge_required: Decimal
    is_profitable: bool
    
    # Risk metrics
    hedge_gap_risk: Decimal
    liquidity_risk_score: Decimal
    
    @property
    def edge_margin(self) -> Decimal:
        """Margin above/below minimum required edge."""
        return self.total_edge - self.min_edge_required
    
    @property
    def edge_ratio(self) -> Decimal:
        """Ratio of actual edge to minimum required."""
        if self.min_edge_required == 0:
            return Decimal('inf') if self.total_edge > 0 else Decimal('-inf')
        return self.total_edge / self.min_edge_required
    
    def to_display_dict(self) -> Dict[str, str]:
        """Convert to human-readable display format."""
        return {
            'Trading Pair': self.trading_pair,
            'Long Exchange': self.exchange_long,
            'Short Exchange': self.exchange_short,
            'Expected Funding': f"{self.expected_funding_pnl:.6f}",
            'Trading Fees': f"-{self.trading_fees_total:.6f}",
            'Borrow Cost': f"-{self.borrow_cost_total:.6f}",
            'Slippage Buffer': f"-{self.slippage_buffer_total:.6f}",
            'Settlement Buffer': f"-{self.settlement_buffer:.6f}",
            'Total Edge': f"{self.total_edge:.6f}",
            'Min Required': f"{self.min_edge_required:.6f}",
            'Edge Margin': f"{self.edge_margin:.6f}",
            'Profitable': "✓" if self.is_profitable else "✗",
            'Notional': f"{self.notional_amount:.2f}",
            'Hedge Gap Risk': f"{self.hedge_gap_risk:.6f}",
        }


class EdgeCalculator:
    """
    Calculates edge decomposition for funding arbitrage opportunities.
    """
    
    def __init__(self, 
                 min_edge_required: Decimal = Decimal("0.0005"),
                 settlement_buffer_bps: Decimal = Decimal("0.0001")):
        self.min_edge_required = min_edge_required
        self.settlement_buffer_bps = settlement_buffer_bps
    
    def calculate_edge(self,
                      trading_pair: str,
                      exchange_long: str,
                      exchange_short: str,
                      funding_rate_long: Decimal,
                      funding_rate_short: Decimal,
                      notional_amount: Decimal,
                      fees_config: Dict[str, Dict[str, Decimal]],
                      borrow_rates: Dict[str, Decimal],
                      slippage_estimates: Dict[str, Decimal],
                      leverage_long: Decimal = Decimal("1"),
                      leverage_short: Decimal = Decimal("1"),
                      funding_period_hours: Decimal = Decimal("8"),
                      timestamp: Optional[float] = None) -> EdgeDecomposition:
        """
        Calculate complete edge decomposition.
        
        Args:
            trading_pair: Trading pair symbol
            exchange_long: Exchange for long position
            exchange_short: Exchange for short position
            funding_rate_long: Funding rate on long exchange
            funding_rate_short: Funding rate on short exchange
            notional_amount: Position size in quote currency
            fees_config: Exchange fee configuration
            borrow_rates: Borrowing rates by asset
            slippage_estimates: Expected slippage by exchange
            leverage_long: Leverage for long position
            leverage_short: Leverage for short position
            funding_period_hours: Hours until next funding settlement
            timestamp: Calculation timestamp
        """
        import time
        if timestamp is None:
            timestamp = time.time()
        
        # Calculate expected funding PnL
        funding_diff = funding_rate_short - funding_rate_long
        expected_funding_pnl = funding_diff * notional_amount
        
        # Calculate trading fees
        fees_breakdown = self._calculate_trading_fees(
            exchange_long, exchange_short, notional_amount, fees_config
        )
        trading_fees_total = sum(fees_breakdown.values())
        
        # Calculate borrow costs
        borrow_breakdown = self._calculate_borrow_costs(
            trading_pair, notional_amount, borrow_rates, 
            leverage_long, leverage_short, funding_period_hours
        )
        borrow_cost_total = sum(borrow_breakdown.values())
        
        # Calculate slippage buffers
        slippage_breakdown = self._calculate_slippage_buffers(
            exchange_long, exchange_short, notional_amount, slippage_estimates
        )
        slippage_buffer_total = sum(slippage_breakdown.values())
        
        # Settlement buffer (protection against funding rate changes)
        settlement_buffer = notional_amount * self.settlement_buffer_bps
        
        # Calculate total edge
        total_edge = (expected_funding_pnl - trading_fees_total - 
                     borrow_cost_total - slippage_buffer_total - settlement_buffer)
        
        # Risk calculations
        hedge_gap_risk = self._calculate_hedge_gap_risk(
            leverage_long, leverage_short, notional_amount
        )
        liquidity_risk_score = self._calculate_liquidity_risk(
            exchange_long, exchange_short, notional_amount
        )
        
        # Determine profitability
        is_profitable = total_edge >= self.min_edge_required
        
        return EdgeDecomposition(
            trading_pair=trading_pair,
            exchange_long=exchange_long,
            exchange_short=exchange_short,
            timestamp=timestamp,
            expected_funding_rate=funding_diff,
            expected_funding_pnl=expected_funding_pnl,
            trading_fees_total=trading_fees_total,
            borrow_cost_total=borrow_cost_total,
            slippage_buffer_total=slippage_buffer_total,
            settlement_buffer=settlement_buffer,
            fees_breakdown=fees_breakdown,
            borrow_breakdown=borrow_breakdown,
            slippage_breakdown=slippage_breakdown,
            notional_amount=notional_amount,
            leverage_long=leverage_long,
            leverage_short=leverage_short,
            total_edge=total_edge,
            min_edge_required=self.min_edge_required,
            is_profitable=is_profitable,
            hedge_gap_risk=hedge_gap_risk,
            liquidity_risk_score=liquidity_risk_score
        )
    
    def _calculate_trading_fees(self,
                               exchange_long: str,
                               exchange_short: str,
                               notional_amount: Decimal,
                               fees_config: Dict[str, Dict[str, Decimal]]) -> Dict[str, Decimal]:
        """Calculate trading fees for both exchanges."""
        fees = {}
        
        for exchange in [exchange_long, exchange_short]:
            if exchange in fees_config:
                # Assuming we need to open and close positions (2x fees)
                maker_fee = fees_config[exchange].get('maker', Decimal("0.001"))
                taker_fee = fees_config[exchange].get('taker', Decimal("0.001"))
                # Conservative estimate using taker fees for both open/close
                fees[f"{exchange}_open"] = notional_amount * taker_fee
                fees[f"{exchange}_close"] = notional_amount * taker_fee
            else:
                # Default fees if not configured
                default_fee = Decimal("0.001")  # 0.1%
                fees[f"{exchange}_open"] = notional_amount * default_fee
                fees[f"{exchange}_close"] = notional_amount * default_fee
        
        return fees
    
    def _calculate_borrow_costs(self,
                               trading_pair: str,
                               notional_amount: Decimal,
                               borrow_rates: Dict[str, Decimal],
                               leverage_long: Decimal,
                               leverage_short: Decimal,
                               funding_period_hours: Decimal) -> Dict[str, Decimal]:
        """Calculate borrowing costs for leveraged positions."""
        costs = {}
        
        # Extract base and quote assets from trading pair
        if '-' in trading_pair:
            base_asset, quote_asset = trading_pair.split('-', 1)
        else:
            # Parse trading pair format like BTCUSDT, ETHUSDC, etc.
            # Check for common 4-char quote currencies first (most specific)
            if trading_pair.endswith(('USDT', 'USDC', 'BUSD', 'TUSD')):
                base_asset = trading_pair[:-4]
                quote_asset = trading_pair[-4:]
            # Then check common 3-char quote currencies
            elif trading_pair.endswith(('USD', 'EUR', 'GBP', 'JPY', 'BTC', 'ETH', 'BNB', 'DAI')):
                base_asset = trading_pair[:-3]
                quote_asset = trading_pair[-3:]
            # Fallback: assume 3-char quote (least common)
            else:
                base_asset = trading_pair[:-3] if len(trading_pair) > 3 else ''
                quote_asset = trading_pair[-3:] if len(trading_pair) > 3 else trading_pair
        
        # Borrow costs for leveraged positions
        if leverage_long > Decimal("1"):
            borrow_amount_long = notional_amount * (leverage_long - Decimal("1")) / leverage_long
            borrow_rate = borrow_rates.get(quote_asset, Decimal("0.0001"))  # Default 0.01% per hour
            costs["long_borrow"] = borrow_amount_long * borrow_rate * (funding_period_hours / Decimal("24"))
        
        if leverage_short > Decimal("1"):
            borrow_amount_short = notional_amount * (leverage_short - Decimal("1")) / leverage_short  
            borrow_rate = borrow_rates.get(base_asset, Decimal("0.0001"))
            costs["short_borrow"] = borrow_amount_short * borrow_rate * (funding_period_hours / Decimal("24"))
        
        return costs
    
    def _calculate_slippage_buffers(self,
                                   exchange_long: str,
                                   exchange_short: str,
                                   notional_amount: Decimal,
                                   slippage_estimates: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Calculate slippage buffers for each exchange."""
        buffers = {}
        
        for exchange in [exchange_long, exchange_short]:
            # Get slippage estimate or use default
            slippage_rate = slippage_estimates.get(exchange, Decimal("0.0005"))  # 0.05% default
            buffers[f"{exchange}_slippage"] = notional_amount * slippage_rate
        
        return buffers
    
    def _calculate_hedge_gap_risk(self,
                                 leverage_long: Decimal,
                                 leverage_short: Decimal,
                                 notional_amount: Decimal) -> Decimal:
        """
        Calculate risk from potential hedge gaps.
        Higher leverage increases execution risk.
        """
        leverage_factor = max(leverage_long, leverage_short)
        base_risk = Decimal("0.0001")  # 0.01% base risk
        return base_risk * leverage_factor * (notional_amount / Decimal("1000"))
    
    def _calculate_liquidity_risk(self,
                                 exchange_long: str,
                                 exchange_short: str,
                                 notional_amount: Decimal) -> Decimal:
        """
        Calculate liquidity risk score based on exchange and position size.
        This would ideally use real-time order book data.
        """
        # Simplified risk scoring - would be enhanced with real market data
        exchange_liquidity_scores = {
            'binance': Decimal("0.1"),
            'bybit': Decimal("0.2"),
            'okx': Decimal("0.15"),
            'gate_io': Decimal("0.3"),
            'kucoin': Decimal("0.25"),
        }
        
        long_risk = exchange_liquidity_scores.get(exchange_long.lower(), Decimal("0.5"))
        short_risk = exchange_liquidity_scores.get(exchange_short.lower(), Decimal("0.5"))
        
        size_factor = min(notional_amount / Decimal("10000"), Decimal("2.0"))  # Scale with size
        
        return (long_risk + short_risk) * size_factor


class EdgeTracker:
    """
    Tracks edge decomposition history for analysis and debugging.
    """
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.edge_history: List[EdgeDecomposition] = []
        self.profitable_count = 0
        self.total_count = 0
    
    def add_edge_calculation(self, edge: EdgeDecomposition):
        """Add new edge calculation to history."""
        self.edge_history.append(edge)
        self.total_count += 1
        
        if edge.is_profitable:
            self.profitable_count += 1
        
        # Maintain history size limit
        if len(self.edge_history) > self.max_history:
            self.edge_history.pop(0)
    
    def get_recent_profitable(self, count: int = 10) -> List[EdgeDecomposition]:
        """Get recent profitable opportunities."""
        profitable = [e for e in self.edge_history if e.is_profitable]
        return profitable[-count:] if profitable else []
    
    def get_profitability_rate(self, lookback_hours: float = 24) -> float:
        """Get profitability rate over specified time window."""
        import time
        cutoff_time = time.time() - (lookback_hours * 3600)
        
        recent_edges = [e for e in self.edge_history if e.timestamp >= cutoff_time]
        if not recent_edges:
            return 0.0
        
        profitable_recent = sum(1 for e in recent_edges if e.is_profitable)
        return profitable_recent / len(recent_edges)
    
    def get_average_edge_components(self) -> Dict[str, Decimal]:
        """Get average values for each edge component."""
        if not self.edge_history:
            return {}
        
        total_edges = len(self.edge_history)
        return {
            'expected_funding': sum(e.expected_funding_pnl for e in self.edge_history) / total_edges,
            'trading_fees': sum(e.trading_fees_total for e in self.edge_history) / total_edges,
            'borrow_costs': sum(e.borrow_cost_total for e in self.edge_history) / total_edges,
            'slippage_buffer': sum(e.slippage_buffer_total for e in self.edge_history) / total_edges,
            'total_edge': sum(e.total_edge for e in self.edge_history) / total_edges,
        }