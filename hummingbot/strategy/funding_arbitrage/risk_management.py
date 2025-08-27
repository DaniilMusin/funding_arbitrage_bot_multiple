"""
Risk management system for funding arbitrage with liquidity buffers,
notional limits, and hedge gap monitoring.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple, NamedTuple
from enum import Enum
import time
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels for position sizing and limits."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LimitType(Enum):
    """Types of risk limits."""
    NOTIONAL_PER_EXCHANGE = "notional_per_exchange"
    NOTIONAL_PER_SUBACCOUNT = "notional_per_subaccount"
    TOTAL_NOTIONAL = "total_notional"
    HEDGE_GAP = "hedge_gap"
    CONCENTRATION = "concentration"
    LEVERAGE = "leverage"


@dataclass
class RiskLimit:
    """Definition of a risk limit."""
    limit_type: LimitType
    max_value: Decimal
    warning_threshold: Decimal  # % of max_value to trigger warning
    description: str
    
    def get_warning_level(self) -> Decimal:
        """Get the value at which warnings should trigger."""
        return self.max_value * self.warning_threshold


@dataclass
class PositionInfo:
    """Information about a position for risk calculations."""
    exchange: str
    subaccount: Optional[str]
    trading_pair: str
    notional_amount: Decimal
    leverage: Decimal
    side: str  # 'long' or 'short'
    timestamp: float
    order_ids: List[str] = field(default_factory=list)


@dataclass
class HedgeGap:
    """Information about hedge gap between paired positions."""
    trading_pair: str
    long_exchange: str
    short_exchange: str
    long_notional: Decimal
    short_notional: Decimal
    gap_amount: Decimal  # Absolute difference
    gap_percentage: Decimal  # Relative to larger position
    timestamp: float
    
    @property
    def gap_risk_score(self) -> Decimal:
        """Calculate risk score based on gap size."""
        base_score = min(self.gap_percentage * Decimal("10"), Decimal("1.0"))
        size_factor = min(self.gap_amount / Decimal("1000"), Decimal("2.0"))
        return base_score * (Decimal("1") + size_factor)


@dataclass
class LiquidityMetrics:
    """Liquidity metrics for an exchange/pair."""
    exchange: str
    trading_pair: str
    bid_depth_1pct: Decimal  # Liquidity within 1% of mid
    ask_depth_1pct: Decimal
    bid_depth_5pct: Decimal  # Liquidity within 5% of mid
    ask_depth_5pct: Decimal
    avg_spread_bps: Decimal  # Average spread in basis points
    impact_score: Decimal   # Impact score for typical position size
    timestamp: float


class RiskManager:
    """
    Comprehensive risk management for funding arbitrage positions.
    Monitors limits, liquidity, and hedge gaps.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.risk_limits = self._initialize_risk_limits()
        self.positions: Dict[str, PositionInfo] = {}  # position_id -> PositionInfo
        self.hedge_pairs: Dict[str, List[str]] = defaultdict(list)  # trading_pair -> [position_ids]
        self.liquidity_cache: Dict[str, LiquidityMetrics] = {}
        self.violation_history: List[Dict] = []
        
    def _initialize_risk_limits(self) -> Dict[LimitType, RiskLimit]:
        """Initialize default risk limits."""
        return {
            LimitType.NOTIONAL_PER_EXCHANGE: RiskLimit(
                limit_type=LimitType.NOTIONAL_PER_EXCHANGE,
                max_value=Decimal(self.config.get('max_notional_per_exchange', '50000')),
                warning_threshold=Decimal('0.8'),
                description="Maximum notional amount per exchange"
            ),
            LimitType.NOTIONAL_PER_SUBACCOUNT: RiskLimit(
                limit_type=LimitType.NOTIONAL_PER_SUBACCOUNT,
                max_value=Decimal(self.config.get('max_notional_per_subaccount', '20000')),
                warning_threshold=Decimal('0.8'),
                description="Maximum notional amount per subaccount"
            ),
            LimitType.TOTAL_NOTIONAL: RiskLimit(
                limit_type=LimitType.TOTAL_NOTIONAL,
                max_value=Decimal(self.config.get('max_total_notional', '200000')),
                warning_threshold=Decimal('0.8'),
                description="Maximum total notional across all positions"
            ),
            LimitType.HEDGE_GAP: RiskLimit(
                limit_type=LimitType.HEDGE_GAP,
                max_value=Decimal(self.config.get('max_hedge_gap_pct', '0.05')),  # 5%
                warning_threshold=Decimal('0.6'),
                description="Maximum hedge gap as percentage of position size"
            ),
            LimitType.CONCENTRATION: RiskLimit(
                limit_type=LimitType.CONCENTRATION,
                max_value=Decimal(self.config.get('max_concentration_pct', '0.3')),  # 30%
                warning_threshold=Decimal('0.8'),
                description="Maximum concentration in single trading pair"
            ),
            LimitType.LEVERAGE: RiskLimit(
                limit_type=LimitType.LEVERAGE,
                max_value=Decimal(self.config.get('max_leverage', '10')),
                warning_threshold=Decimal('0.8'),
                description="Maximum leverage per position"
            ),
        }
    
    def check_position_limits(self, 
                            exchange: str,
                            subaccount: Optional[str],
                            trading_pair: str,
                            proposed_notional: Decimal,
                            proposed_leverage: Decimal) -> Tuple[bool, List[str], RiskLevel]:
        """
        Check if a proposed position would violate risk limits.
        
        Returns:
            Tuple of (can_open, violation_messages, risk_level)
        """
        violations = []
        warnings = []
        
        # Check leverage limit
        leverage_limit = self.risk_limits[LimitType.LEVERAGE]
        if proposed_leverage > leverage_limit.max_value:
            violations.append(
                f"Leverage {proposed_leverage} exceeds limit {leverage_limit.max_value}"
            )
        elif proposed_leverage > leverage_limit.get_warning_level():
            warnings.append(
                f"Leverage {proposed_leverage} approaching limit {leverage_limit.max_value}"
            )
        
        # Check notional per exchange
        exchange_notional = self._get_exchange_notional(exchange) + proposed_notional
        exchange_limit = self.risk_limits[LimitType.NOTIONAL_PER_EXCHANGE]
        if exchange_notional > exchange_limit.max_value:
            violations.append(
                f"Exchange {exchange} notional {exchange_notional} exceeds limit {exchange_limit.max_value}"
            )
        elif exchange_notional > exchange_limit.get_warning_level():
            warnings.append(
                f"Exchange {exchange} notional {exchange_notional} approaching limit"
            )
        
        # Check notional per subaccount
        if subaccount:
            subaccount_notional = self._get_subaccount_notional(exchange, subaccount) + proposed_notional
            subaccount_limit = self.risk_limits[LimitType.NOTIONAL_PER_SUBACCOUNT]
            if subaccount_notional > subaccount_limit.max_value:
                violations.append(
                    f"Subaccount {subaccount} notional {subaccount_notional} exceeds limit {subaccount_limit.max_value}"
                )
            elif subaccount_notional > subaccount_limit.get_warning_level():
                warnings.append(
                    f"Subaccount {subaccount} notional approaching limit"
                )
        
        # Check total notional
        total_notional = self._get_total_notional() + proposed_notional
        total_limit = self.risk_limits[LimitType.TOTAL_NOTIONAL]
        if total_notional > total_limit.max_value:
            violations.append(
                f"Total notional {total_notional} exceeds limit {total_limit.max_value}"
            )
        elif total_notional > total_limit.get_warning_level():
            warnings.append(f"Total notional approaching limit")
        
        # Check concentration
        pair_notional = self._get_pair_notional(trading_pair) + proposed_notional
        concentration_pct = pair_notional / total_notional if total_notional > 0 else Decimal('0')
        concentration_limit = self.risk_limits[LimitType.CONCENTRATION]
        if concentration_pct > concentration_limit.max_value:
            violations.append(
                f"Concentration in {trading_pair} ({concentration_pct:.1%}) exceeds limit {concentration_limit.max_value:.1%}"
            )
        elif concentration_pct > concentration_limit.get_warning_level():
            warnings.append(f"Concentration in {trading_pair} approaching limit")
        
        # Determine risk level
        if violations:
            risk_level = RiskLevel.CRITICAL
            can_open = False
        elif len(warnings) >= 3:
            risk_level = RiskLevel.HIGH
            can_open = True
        elif len(warnings) >= 1:
            risk_level = RiskLevel.MEDIUM
            can_open = True
        else:
            risk_level = RiskLevel.LOW
            can_open = True
        
        all_messages = violations + warnings
        
        return can_open, all_messages, risk_level
    
    def check_liquidity_risk(self, 
                           exchange: str, 
                           trading_pair: str,
                           notional_amount: Decimal) -> Tuple[bool, str, Decimal]:
        """
        Check liquidity risk for a position size.
        
        Returns:
            Tuple of (is_acceptable, reason, impact_score)
        """
        liquidity = self.liquidity_cache.get(f"{exchange}_{trading_pair}")
        
        if not liquidity:
            return False, "No liquidity data available", Decimal('1.0')
        
        # Check if position size fits within available liquidity
        available_liquidity = min(liquidity.bid_depth_1pct, liquidity.ask_depth_1pct)
        
        if notional_amount > available_liquidity * Decimal('0.8'):  # Use max 80% of available
            return False, f"Position size {notional_amount} exceeds safe liquidity limit {available_liquidity * Decimal('0.8')}", Decimal('1.0')
        
        # Calculate impact score
        impact_ratio = notional_amount / available_liquidity
        impact_score = min(impact_ratio * Decimal('2'), Decimal('1.0'))
        
        if impact_score > Decimal('0.5'):
            return False, f"High market impact expected: {impact_score:.2%}", impact_score
        
        return True, f"Acceptable liquidity risk: {impact_score:.2%} impact", impact_score
    
    def add_position(self, position: PositionInfo) -> str:
        """
        Add a new position to tracking.
        
        Returns:
            Position ID for tracking
        """
        position_id = f"{position.exchange}_{position.trading_pair}_{position.side}_{int(time.time())}"
        self.positions[position_id] = position
        self.hedge_pairs[position.trading_pair].append(position_id)
        
        logger.info(f"Added position {position_id}: {position.notional_amount} {position.trading_pair} on {position.exchange}")
        
        return position_id
    
    def remove_position(self, position_id: str):
        """Remove a position from tracking."""
        if position_id in self.positions:
            position = self.positions[position_id]
            del self.positions[position_id]
            
            if position_id in self.hedge_pairs[position.trading_pair]:
                self.hedge_pairs[position.trading_pair].remove(position_id)
                
            logger.info(f"Removed position {position_id}")
    
    def update_liquidity_metrics(self, metrics: LiquidityMetrics):
        """Update liquidity metrics for an exchange/pair."""
        key = f"{metrics.exchange}_{metrics.trading_pair}"
        self.liquidity_cache[key] = metrics
    
    def calculate_hedge_gaps(self) -> List[HedgeGap]:
        """Calculate current hedge gaps for all trading pairs."""
        gaps = []
        
        for trading_pair, position_ids in self.hedge_pairs.items():
            if len(position_ids) < 2:
                continue  # No hedge to calculate
            
            # Group positions by exchange and side
            exchange_positions = defaultdict(list)
            for pos_id in position_ids:
                if pos_id not in self.positions:
                    continue
                position = self.positions[pos_id]
                key = f"{position.exchange}_{position.side}"
                exchange_positions[key].append(position)
            
            # Find hedge pairs (long vs short)
            longs = []
            shorts = []
            
            for key, positions in exchange_positions.items():
                exchange, side = key.rsplit('_', 1)
                total_notional = sum(p.notional_amount for p in positions)
                
                if side == 'long':
                    longs.append((exchange, total_notional))
                else:
                    shorts.append((exchange, total_notional))
            
            # Calculate gaps between all long/short pairs
            for long_exchange, long_notional in longs:
                for short_exchange, short_notional in shorts:
                    if long_exchange == short_exchange:
                        continue  # Same exchange
                    
                    gap_amount = abs(long_notional - short_notional)
                    larger_position = max(long_notional, short_notional)
                    gap_percentage = gap_amount / larger_position if larger_position > 0 else Decimal('0')
                    
                    gap = HedgeGap(
                        trading_pair=trading_pair,
                        long_exchange=long_exchange,
                        short_exchange=short_exchange,
                        long_notional=long_notional,
                        short_notional=short_notional,
                        gap_amount=gap_amount,
                        gap_percentage=gap_percentage,
                        timestamp=time.time()
                    )
                    
                    gaps.append(gap)
        
        return gaps
    
    def check_hedge_gap_violations(self) -> List[Tuple[HedgeGap, str]]:
        """Check for hedge gap violations."""
        gaps = self.calculate_hedge_gaps()
        violations = []
        
        gap_limit = self.risk_limits[LimitType.HEDGE_GAP]
        
        for gap in gaps:
            if gap.gap_percentage > gap_limit.max_value:
                violations.append((
                    gap,
                    f"Hedge gap {gap.gap_percentage:.2%} exceeds limit {gap_limit.max_value:.2%} for {gap.trading_pair}"
                ))
            elif gap.gap_percentage > gap_limit.get_warning_level():
                violations.append((
                    gap,
                    f"Hedge gap {gap.gap_percentage:.2%} approaching limit for {gap.trading_pair}"
                ))
        
        return violations
    
    def get_risk_summary(self) -> Dict:
        """Get comprehensive risk summary."""
        hedge_gaps = self.calculate_hedge_gaps()
        gap_violations = self.check_hedge_gap_violations()
        
        return {
            'total_positions': len(self.positions),
            'total_notional': self._get_total_notional(),
            'exchange_exposures': self._get_exchange_exposures(),
            'pair_concentrations': self._get_pair_concentrations(),
            'hedge_gaps': len(hedge_gaps),
            'gap_violations': len(gap_violations),
            'max_gap': max((g.gap_percentage for g in hedge_gaps), default=Decimal('0')),
            'liquidity_pairs': len(self.liquidity_cache),
            'risk_limit_utilization': self._get_limit_utilization(),
        }
    
    def _get_exchange_notional(self, exchange: str) -> Decimal:
        """Get total notional for an exchange."""
        return sum(
            pos.notional_amount for pos in self.positions.values()
            if pos.exchange == exchange
        )
    
    def _get_subaccount_notional(self, exchange: str, subaccount: str) -> Decimal:
        """Get total notional for a subaccount."""
        return sum(
            pos.notional_amount for pos in self.positions.values()
            if pos.exchange == exchange and pos.subaccount == subaccount
        )
    
    def _get_total_notional(self) -> Decimal:
        """Get total notional across all positions."""
        return sum(pos.notional_amount for pos in self.positions.values())
    
    def _get_pair_notional(self, trading_pair: str) -> Decimal:
        """Get total notional for a trading pair."""
        return sum(
            pos.notional_amount for pos in self.positions.values()
            if pos.trading_pair == trading_pair
        )
    
    def _get_exchange_exposures(self) -> Dict[str, Decimal]:
        """Get notional exposure by exchange."""
        exposures = defaultdict(Decimal)
        for pos in self.positions.values():
            exposures[pos.exchange] += pos.notional_amount
        return dict(exposures)
    
    def _get_pair_concentrations(self) -> Dict[str, Decimal]:
        """Get concentration percentages by trading pair."""
        total = self._get_total_notional()
        if total == 0:
            return {}
        
        concentrations = defaultdict(Decimal)
        for pos in self.positions.values():
            concentrations[pos.trading_pair] += pos.notional_amount
        
        return {pair: notional / total for pair, notional in concentrations.items()}
    
    def _get_limit_utilization(self) -> Dict[str, Decimal]:
        """Get utilization percentage for each risk limit."""
        utilization = {}
        
        # Exchange limits
        for exchange in set(pos.exchange for pos in self.positions.values()):
            exchange_notional = self._get_exchange_notional(exchange)
            limit = self.risk_limits[LimitType.NOTIONAL_PER_EXCHANGE].max_value
            utilization[f"exchange_{exchange}"] = exchange_notional / limit
        
        # Total notional
        total_notional = self._get_total_notional()
        total_limit = self.risk_limits[LimitType.TOTAL_NOTIONAL].max_value
        utilization["total_notional"] = total_notional / total_limit
        
        # Concentration
        concentrations = self._get_pair_concentrations()
        concentration_limit = self.risk_limits[LimitType.CONCENTRATION].max_value
        for pair, concentration in concentrations.items():
            utilization[f"concentration_{pair}"] = concentration / concentration_limit
        
        return utilization