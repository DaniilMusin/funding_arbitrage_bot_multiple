"""
Margin call and ADL protection system for funding arbitrage.
Monitors leverage levels, margin requirements, and responds to exchange changes.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Callable, Any
from enum import Enum
import time
import logging
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


class MarginStatus(Enum):
    """Margin health status levels."""
    HEALTHY = "healthy"          # >200% margin ratio
    WARNING = "warning"          # 150-200% margin ratio
    DANGER = "danger"           # 110-150% margin ratio
    CRITICAL = "critical"       # 100-110% margin ratio
    LIQUIDATION_RISK = "liquidation_risk"  # <100% margin ratio


class ADLRisk(Enum):
    """Auto-deleveraging risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IMMINENT = "imminent"


class MarginAction(Enum):
    """Actions to take based on margin status."""
    MONITOR = "monitor"
    REDUCE_LEVERAGE = "reduce_leverage"
    CLOSE_POSITIONS = "close_positions"
    ADD_MARGIN = "add_margin"
    EMERGENCY_EXIT = "emergency_exit"


@dataclass
class MarginInfo:
    """Margin information for a position or account."""
    exchange: str
    account_id: Optional[str]
    total_equity: Decimal
    used_margin: Decimal
    free_margin: Decimal
    margin_ratio: Decimal  # total_equity / used_margin
    maintenance_margin: Decimal
    initial_margin_req: Decimal
    liquidation_price: Optional[Decimal]
    timestamp: float

    @property
    def margin_health(self) -> MarginStatus:
        """Determine margin health status."""
        if self.margin_ratio >= Decimal("2.0"):
            return MarginStatus.HEALTHY
        elif self.margin_ratio >= Decimal("1.5"):
            return MarginStatus.WARNING
        elif self.margin_ratio >= Decimal("1.1"):
            return MarginStatus.DANGER
        elif self.margin_ratio >= Decimal("1.0"):
            return MarginStatus.CRITICAL
        else:
            return MarginStatus.LIQUIDATION_RISK

    @property
    def utilization_percentage(self) -> Decimal:
        """Calculate margin utilization percentage."""
        if self.total_equity == 0:
            return Decimal("0")
        return (self.used_margin / self.total_equity) * Decimal("100")


@dataclass
class PositionMarginInfo:
    """Margin info specific to a position."""
    position_id: str
    exchange: str
    trading_pair: str
    side: str
    size: Decimal
    notional_value: Decimal
    leverage: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal
    unrealized_pnl: Decimal
    liquidation_price: Optional[Decimal]
    current_mark_price: Optional[Decimal]  # Current mark price for the position
    adl_indicator: Optional[int]  # ADL indicator if available (1-5, 5 being highest risk)
    timestamp: float

    @property
    def margin_used_ratio(self) -> Decimal:
        """Ratio of margin used vs available."""
        if self.initial_margin == 0:
            return Decimal("0")
        return self.maintenance_margin / self.initial_margin

    @property
    def distance_to_liquidation_pct(self) -> Optional[Decimal]:
        """
        Distance to liquidation as percentage of current mark price.

        Returns:
            Percentage distance to liquidation price (positive = safe, negative = in danger)
            None if liquidation price or current price is not available
        """
        if not self.liquidation_price or not self.current_mark_price:
            return None

        if self.current_mark_price == 0:
            return None

        # Calculate distance based on position side
        if self.side.lower() == 'long':
            # For long: liquidation when price drops below liquidation_price
            # Distance = (current_price - liquidation_price) / current_price
            distance = self.current_mark_price - self.liquidation_price
            distance_pct = (distance / self.current_mark_price) * Decimal("100")
        else:  # short
            # For short: liquidation when price rises above liquidation_price
            # Distance = (liquidation_price - current_price) / current_price
            distance = self.liquidation_price - self.current_mark_price
            distance_pct = (distance / self.current_mark_price) * Decimal("100")

        return distance_pct


@dataclass
class ExchangeMarginRequirements:
    """Margin requirements for a specific exchange."""
    exchange: str
    initial_margin_rates: Dict[str, Decimal]  # symbol -> rate
    maintenance_margin_rates: Dict[str, Decimal]  # symbol -> rate
    max_leverage: Dict[str, Decimal]  # symbol -> max leverage
    liquidation_fee_rate: Decimal
    adl_enabled: bool
    margin_mode: str  # 'cross' or 'isolated'
    tier_system: Optional[Dict[str, List[Tuple[Decimal, Decimal]]]]  # symbol -> [(notional, rate)]
    last_updated: float

    def get_initial_margin_rate(self, symbol: str, notional: Decimal) -> Decimal:
        """Get initial margin rate for symbol/size."""
        if self.tier_system and symbol in self.tier_system:
            # Find appropriate tier
            tiers = self.tier_system[symbol]

            # SAFETY: Check if tiers is not empty
            if not tiers:
                return self.initial_margin_rates.get(symbol, Decimal("0.1"))

            for tier_notional, tier_rate in tiers:
                if notional <= tier_notional:
                    return tier_rate
            return tiers[-1][1]  # Use highest tier rate

        return self.initial_margin_rates.get(symbol, Decimal("0.1"))  # 10% default

    def get_maintenance_margin_rate(self, symbol: str, notional: Decimal) -> Decimal:
        """Get maintenance margin rate for symbol/size."""
        if self.tier_system and symbol in self.tier_system:
            tiers = self.tier_system[symbol]

            # SAFETY: Check if tiers is not empty
            if not tiers:
                return self.maintenance_margin_rates.get(symbol, Decimal("0.05"))

            for tier_notional, tier_rate in tiers:
                if notional <= tier_notional:
                    return tier_rate * Decimal("0.5")  # Typically ~50% of initial
            return tiers[-1][1] * Decimal("0.5")

        return self.maintenance_margin_rates.get(symbol, Decimal("0.05"))  # 5% default


class MarginMonitor:
    """
    Monitors margin health across all exchanges and positions.
    Provides early warning and automatic protection mechanisms.
    """

    def __init__(self,
                 safety_buffer: Decimal = Decimal("0.2"),  # Keep 20% buffer above maintenance
                 max_allowed_leverage: Decimal = Decimal("5"),
                 auto_reduce_enabled: bool = True):
        self.safety_buffer = safety_buffer
        self.max_allowed_leverage = max_allowed_leverage
        self.auto_reduce_enabled = auto_reduce_enabled

        self.exchange_requirements: Dict[str, ExchangeMarginRequirements] = {}
        self.margin_snapshots: Dict[str, MarginInfo] = {}
        self.position_margins: Dict[str, PositionMarginInfo] = {}
        self.alert_callbacks: List[Callable] = []
        self.action_callbacks: Dict[MarginAction, List[Callable]] = defaultdict(list)

        self.monitoring_active = False
        self.last_check_time = 0
        self.check_interval = 30  # seconds

    def register_alert_callback(self, callback: Callable[[MarginStatus, Dict], None]):
        """Register callback for margin alerts."""
        self.alert_callbacks.append(callback)

    def register_action_callback(self, action: MarginAction, callback: Callable):
        """Register callback for specific margin actions."""
        self.action_callbacks[action].append(callback)

    def update_exchange_requirements(self, requirements: ExchangeMarginRequirements):
        """Update margin requirements for an exchange."""
        self.exchange_requirements[requirements.exchange] = requirements
        logger.info(f"Updated margin requirements for {requirements.exchange}")

    def update_margin_info(self, margin_info: MarginInfo):
        """Update margin information for an account."""
        key = f"{margin_info.exchange}_{margin_info.account_id or 'default'}"
        self.margin_snapshots[key] = margin_info

        # Check for immediate alerts
        self._check_margin_alerts(margin_info)

    def update_position_margin(self, position_margin: PositionMarginInfo):
        """Update margin information for a specific position."""
        self.position_margins[position_margin.position_id] = position_margin

        # Check position-specific alerts
        self._check_position_margin_alerts(position_margin)

    def calculate_safe_leverage(self,
                              exchange: str,
                              symbol: str,
                              notional: Decimal) -> Decimal:
        """
        Calculate maximum safe leverage for a position.

        Args:
            exchange: Exchange name
            symbol: Trading pair symbol
            notional: Position notional value

        Returns:
            Maximum safe leverage to use
        """
        requirements = self.exchange_requirements.get(exchange)
        if not requirements:
            return min(self.max_allowed_leverage, Decimal("3"))  # Conservative default

        # Get margin rates
        initial_rate = requirements.get_initial_margin_rate(symbol, notional)
        maintenance_rate = requirements.get_maintenance_margin_rate(symbol, notional)

        # Calculate max leverage based on exchange limits
        max_exchange_leverage = requirements.max_leverage.get(symbol, Decimal("10"))

        # Calculate safe leverage with buffer
        # safe_leverage = 1 / (maintenance_rate * (1 + safety_buffer))
        safe_leverage = Decimal("1") / (maintenance_rate * (Decimal("1") + self.safety_buffer))

        # Apply limits
        final_leverage = min(
            safe_leverage,
            max_exchange_leverage,
            self.max_allowed_leverage
        )

        logger.debug(f"Safe leverage for {symbol} on {exchange}: {final_leverage} (rates: init={initial_rate}, maint={maintenance_rate})")

        return final_leverage

    def check_leverage_reduction_needed(self,
                                      position_id: str) -> Tuple[bool, Optional[Decimal]]:
        """
        Check if leverage reduction is needed for a position.

        Returns:
            Tuple of (needs_reduction, suggested_new_leverage)
        """
        if position_id not in self.position_margins:
            return False, None

        position = self.position_margins[position_id]

        # Check if current leverage is too high
        safe_leverage = self.calculate_safe_leverage(
            position.exchange,
            position.trading_pair,
            position.notional_value
        )

        if position.leverage > safe_leverage:
            return True, safe_leverage

        # Check margin health
        account_key = f"{position.exchange}_default"
        if account_key in self.margin_snapshots:
            margin_info = self.margin_snapshots[account_key]
            if margin_info.margin_health in [MarginStatus.DANGER, MarginStatus.CRITICAL]:
                # Reduce leverage more aggressively
                conservative_leverage = safe_leverage * Decimal("0.8")
                return True, conservative_leverage

        return False, None

    def get_adl_risk_assessment(self, position_id: str) -> ADLRisk:
        """Assess ADL risk for a position."""
        if position_id not in self.position_margins:
            return ADLRisk.LOW

        position = self.position_margins[position_id]

        # Check ADL indicator if available
        if position.adl_indicator:
            if position.adl_indicator >= 5:
                return ADLRisk.IMMINENT
            elif position.adl_indicator >= 4:
                return ADLRisk.HIGH
            elif position.adl_indicator >= 3:
                return ADLRisk.MEDIUM
            else:
                return ADLRisk.LOW

        # Estimate based on leverage and margin health
        if position.leverage >= Decimal("8"):
            return ADLRisk.HIGH
        elif position.leverage >= Decimal("5"):
            return ADLRisk.MEDIUM
        else:
            return ADLRisk.LOW

    def get_recommended_actions(self,
                              exchange: str,
                              account_id: Optional[str] = None) -> List[Tuple[MarginAction, str]]:
        """Get recommended actions based on current margin status."""
        key = f"{exchange}_{account_id or 'default'}"
        if key not in self.margin_snapshots:
            return []

        margin_info = self.margin_snapshots[key]
        actions = []

        status = margin_info.margin_health

        if status == MarginStatus.LIQUIDATION_RISK:
            actions.append((MarginAction.EMERGENCY_EXIT, "Immediate liquidation risk - close all positions"))
            actions.append((MarginAction.ADD_MARGIN, "Add funds to prevent liquidation"))

        elif status == MarginStatus.CRITICAL:
            actions.append((MarginAction.CLOSE_POSITIONS, "Close some positions to reduce margin usage"))
            actions.append((MarginAction.ADD_MARGIN, "Add funds to improve margin ratio"))

        elif status == MarginStatus.DANGER:
            actions.append((MarginAction.REDUCE_LEVERAGE, "Reduce leverage on existing positions"))
            actions.append((MarginAction.CLOSE_POSITIONS, "Consider closing riskiest positions"))

        elif status == MarginStatus.WARNING:
            actions.append((MarginAction.REDUCE_LEVERAGE, "Consider reducing leverage"))
            actions.append((MarginAction.MONITOR, "Monitor closely for deterioration"))

        else:  # HEALTHY
            actions.append((MarginAction.MONITOR, "Continue monitoring"))

        return actions

    async def run_monitoring_loop(self):
        """Run continuous margin monitoring."""
        self.monitoring_active = True

        while self.monitoring_active:
            try:
                await self._perform_monitoring_check()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in margin monitoring loop: {e}")
                await asyncio.sleep(min(self.check_interval, 60))

    def stop_monitoring(self):
        """Stop the monitoring loop."""
        self.monitoring_active = False

    async def _perform_monitoring_check(self):
        """Perform a comprehensive margin monitoring check."""
        current_time = time.time()

        # Check all margin snapshots
        critical_accounts = []
        warning_accounts = []

        for key, margin_info in self.margin_snapshots.items():
            status = margin_info.margin_health

            if status in [MarginStatus.LIQUIDATION_RISK, MarginStatus.CRITICAL]:
                critical_accounts.append((key, margin_info))
            elif status in [MarginStatus.DANGER, MarginStatus.WARNING]:
                warning_accounts.append((key, margin_info))

        # Take actions for critical accounts
        for key, margin_info in critical_accounts:
            await self._handle_critical_margin(key, margin_info)

        # Send warnings for warning accounts
        for key, margin_info in warning_accounts:
            await self._handle_warning_margin(key, margin_info)

        # Check for positions needing leverage reduction
        if self.auto_reduce_enabled:
            await self._check_auto_leverage_reduction()

        self.last_check_time = current_time

    def _check_margin_alerts(self, margin_info: MarginInfo):
        """Check and trigger margin alerts."""
        status = margin_info.margin_health

        if status in [MarginStatus.DANGER, MarginStatus.CRITICAL, MarginStatus.LIQUIDATION_RISK]:
            alert_data = {
                'exchange': margin_info.exchange,
                'account_id': margin_info.account_id,
                'margin_ratio': margin_info.margin_ratio,
                'utilization': margin_info.utilization_percentage,
                'status': status.value
            }

            for callback in self.alert_callbacks:
                try:
                    callback(status, alert_data)
                except Exception as e:
                    logger.error(f"Error in margin alert callback: {e}")

    def _check_position_margin_alerts(self, position_margin: PositionMarginInfo):
        """Check position-specific margin alerts."""
        needs_reduction, new_leverage = self.check_leverage_reduction_needed(position_margin.position_id)

        if needs_reduction:
            logger.warning(f"Position {position_margin.position_id} needs leverage reduction: {position_margin.leverage} -> {new_leverage}")

            # Trigger callbacks
            for callback in self.action_callbacks[MarginAction.REDUCE_LEVERAGE]:
                try:
                    callback(position_margin.position_id, new_leverage)
                except Exception as e:
                    logger.error(f"Error in leverage reduction callback: {e}")

    async def _handle_critical_margin(self, account_key: str, margin_info: MarginInfo):
        """Handle critical margin situations."""
        logger.critical(f"Critical margin situation for {account_key}: ratio={margin_info.margin_ratio}")

        # Trigger emergency actions
        for callback in self.action_callbacks[MarginAction.EMERGENCY_EXIT]:
            try:
                await callback(account_key, margin_info)
            except Exception as e:
                logger.error(f"Error in emergency exit callback: {e}")

    async def _handle_warning_margin(self, account_key: str, margin_info: MarginInfo):
        """Handle margin warning situations."""
        logger.warning(f"Margin warning for {account_key}: ratio={margin_info.margin_ratio}")

        # Trigger warning actions
        for callback in self.action_callbacks[MarginAction.REDUCE_LEVERAGE]:
            try:
                await callback(account_key, margin_info)
            except Exception as e:
                logger.error(f"Error in reduce leverage callback: {e}")

    async def _check_auto_leverage_reduction(self):
        """Check all positions for automatic leverage reduction."""
        for position_id, position_info in self.position_margins.items():
            needs_reduction, new_leverage = self.check_leverage_reduction_needed(position_id)

            if needs_reduction and new_leverage:
                logger.info(f"Auto-reducing leverage for {position_id}: {position_info.leverage} -> {new_leverage}")

                # Trigger leverage reduction
                for callback in self.action_callbacks[MarginAction.REDUCE_LEVERAGE]:
                    try:
                        await callback(position_id, new_leverage)
                    except Exception as e:
                        logger.error(f"Error in auto leverage reduction: {e}")

    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get summary of current monitoring status."""
        total_accounts = len(self.margin_snapshots)
        total_positions = len(self.position_margins)

        status_counts = defaultdict(int)
        for margin_info in self.margin_snapshots.values():
            status_counts[margin_info.margin_health.value] += 1

        adl_risk_counts = defaultdict(int)
        for position_id in self.position_margins.keys():
            adl_risk = self.get_adl_risk_assessment(position_id)
            adl_risk_counts[adl_risk.value] += 1

        return {
            'monitoring_active': self.monitoring_active,
            'last_check_time': self.last_check_time,
            'total_accounts': total_accounts,
            'total_positions': total_positions,
            'margin_status_counts': dict(status_counts),
            'adl_risk_counts': dict(adl_risk_counts),
            'auto_reduce_enabled': self.auto_reduce_enabled,
            'configured_exchanges': list(self.exchange_requirements.keys()),
        }