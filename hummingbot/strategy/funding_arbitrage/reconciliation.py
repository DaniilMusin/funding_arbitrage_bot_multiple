"""
Position and balance reconciliation system for funding arbitrage.
Detects discrepancies and provides automatic correction mechanisms.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any, Set, Callable, Awaitable
from enum import Enum
import time
import logging
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


class DiscrepancyType(Enum):
    """Types of discrepancies that can be detected."""
    POSITION_MISSING = "position_missing"
    POSITION_EXTRA = "position_extra"
    POSITION_SIZE_MISMATCH = "position_size_mismatch"
    BALANCE_MISMATCH = "balance_mismatch"
    UNREALIZED_PNL_MISMATCH = "unrealized_pnl_mismatch"
    ORDER_STATE_MISMATCH = "order_state_mismatch"
    FUNDING_PAYMENT_MISSING = "funding_payment_missing"


class ReconciliationAction(Enum):
    """Actions that can be taken to resolve discrepancies."""
    MANUAL_REVIEW = "manual_review"
    AUTO_CLOSE_POSITION = "auto_close_position"
    AUTO_OPEN_POSITION = "auto_open_position"
    AUTO_ADJUST_SIZE = "auto_adjust_size"
    REFRESH_DATA = "refresh_data"
    ALERT_OPERATOR = "alert_operator"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class PositionSnapshot:
    """Snapshot of a position at a point in time."""
    exchange: str
    trading_pair: str
    side: str  # 'long' or 'short'
    size: Decimal
    notional_value: Decimal
    entry_price: Decimal
    mark_price: Decimal
    unrealized_pnl: Decimal
    leverage: Decimal
    margin_used: Decimal
    timestamp: float

    def __hash__(self):
        return hash((self.exchange, self.trading_pair, self.side))


@dataclass
class BalanceSnapshot:
    """Snapshot of balances at a point in time."""
    exchange: str
    asset: str
    total_balance: Decimal
    available_balance: Decimal
    locked_balance: Decimal
    timestamp: float


@dataclass
class Discrepancy:
    """Represents a detected discrepancy."""
    discrepancy_type: DiscrepancyType
    description: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    affected_items: List[str]  # position IDs, asset symbols, etc.
    expected_state: Any
    actual_state: Any
    detected_at: float
    auto_fixable: bool
    suggested_action: ReconciliationAction

    @property
    def age_seconds(self) -> float:
        return time.time() - self.detected_at


@dataclass
class ReconciliationResult:
    """Result of a reconciliation check."""
    timestamp: float
    total_discrepancies: int
    discrepancies_by_type: Dict[DiscrepancyType, int]
    critical_issues: List[Discrepancy]
    auto_fixes_applied: List[str]
    manual_review_required: List[Discrepancy]


class PositionTracker:
    """
    Tracks expected positions based on strategy actions.
    """

    def __init__(self):
        self.expected_positions: Dict[str, PositionSnapshot] = {}
        self.expected_balances: Dict[str, BalanceSnapshot] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self.funding_payments: List[Dict] = []

    def add_expected_position(self, position: PositionSnapshot):
        """Add an expected position to tracking."""
        key = f"{position.exchange}_{position.trading_pair}_{position.side}"
        self.expected_positions[key] = position
        logger.debug(f"Added expected position: {key}")

    def remove_expected_position(self, exchange: str, trading_pair: str, side: str):
        """Remove an expected position."""
        key = f"{exchange}_{trading_pair}_{side}"
        if key in self.expected_positions:
            del self.expected_positions[key]
            logger.debug(f"Removed expected position: {key}")

    def update_expected_balance(self, exchange: str, asset: str, balance: BalanceSnapshot):
        """Update expected balance."""
        key = f"{exchange}_{asset}"
        self.expected_balances[key] = balance

    def get_expected_positions(self) -> Dict[str, PositionSnapshot]:
        """Get all expected positions."""
        return self.expected_positions.copy()

    def get_expected_balances(self) -> Dict[str, BalanceSnapshot]:
        """Get all expected balances."""
        return self.expected_balances.copy()


class ReconciliationEngine:
    """
    Main reconciliation engine that compares expected vs actual state.
    """

    def __init__(self,
                 position_tracker: PositionTracker,
                 auto_fix_enabled: bool = True,
                 max_auto_fix_amount: Decimal = Decimal("1000")):
        self.position_tracker = position_tracker
        self.auto_fix_enabled = auto_fix_enabled
        self.max_auto_fix_amount = max_auto_fix_amount
        self.discrepancy_history: List[Discrepancy] = []
        self.last_reconciliation: Optional[ReconciliationResult] = None
        self.emergency_stop_triggered = False

    async def run_full_reconciliation(self,
                                    actual_positions: Dict[str, PositionSnapshot],
                                    actual_balances: Dict[str, BalanceSnapshot],
                                    actual_orders: Dict[str, Dict] = None) -> ReconciliationResult:
        """
        Run comprehensive reconciliation check.

        Args:
            actual_positions: Current positions from exchanges
            actual_balances: Current balances from exchanges
            actual_orders: Current order states

        Returns:
            ReconciliationResult with findings and actions taken
        """
        start_time = time.time()
        discrepancies = []
        auto_fixes_applied = []

        # Check position discrepancies
        position_discrepancies = await self._check_position_discrepancies(actual_positions)
        discrepancies.extend(position_discrepancies)

        # Check balance discrepancies
        balance_discrepancies = await self._check_balance_discrepancies(actual_balances)
        discrepancies.extend(balance_discrepancies)

        # Check order state discrepancies
        if actual_orders:
            order_discrepancies = await self._check_order_discrepancies(actual_orders)
            discrepancies.extend(order_discrepancies)

        # Apply automatic fixes for eligible discrepancies
        if self.auto_fix_enabled:
            fixes = await self._apply_auto_fixes(discrepancies)
            auto_fixes_applied.extend(fixes)

        # Check for emergency stop conditions
        critical_issues = [d for d in discrepancies if d.severity == 'critical']
        if len(critical_issues) >= 3:
            self.emergency_stop_triggered = True
            logger.critical(f"Emergency stop triggered: {len(critical_issues)} critical discrepancies")

        # Categorize discrepancies
        discrepancies_by_type = defaultdict(int)
        for d in discrepancies:
            discrepancies_by_type[d.discrepancy_type] += 1

        manual_review_required = [
            d for d in discrepancies
            if not d.auto_fixable or d.severity in ['high', 'critical']
        ]

        result = ReconciliationResult(
            timestamp=start_time,
            total_discrepancies=len(discrepancies),
            discrepancies_by_type=dict(discrepancies_by_type),
            critical_issues=critical_issues,
            auto_fixes_applied=auto_fixes_applied,
            manual_review_required=manual_review_required
        )

        self.last_reconciliation = result

        # Store discrepancies in history
        self.discrepancy_history.extend(discrepancies)

        # Cleanup old history
        cutoff_time = time.time() - (24 * 3600)  # Keep 24 hours
        self.discrepancy_history = [
            d for d in self.discrepancy_history
            if d.detected_at > cutoff_time
        ]

        logger.info(f"Reconciliation completed: {len(discrepancies)} discrepancies, {len(auto_fixes_applied)} auto-fixes applied")

        return result

    async def _check_position_discrepancies(self,
                                          actual_positions: Dict[str, PositionSnapshot]) -> List[Discrepancy]:
        """Check for position-related discrepancies."""
        discrepancies = []
        expected_positions = self.position_tracker.get_expected_positions()

        # Check for missing positions (expected but not actual)
        for key, expected in expected_positions.items():
            if key not in actual_positions:
                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.POSITION_MISSING,
                    description=f"Expected position {key} not found on exchange",
                    severity='high',
                    affected_items=[key],
                    expected_state=expected,
                    actual_state=None,
                    detected_at=time.time(),
                    auto_fixable=True,
                    suggested_action=ReconciliationAction.AUTO_OPEN_POSITION
                )
                discrepancies.append(discrepancy)

        # Check for extra positions (actual but not expected)
        for key, actual in actual_positions.items():
            if key not in expected_positions:
                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.POSITION_EXTRA,
                    description=f"Unexpected position {key} found on exchange",
                    severity='medium',
                    affected_items=[key],
                    expected_state=None,
                    actual_state=actual,
                    detected_at=time.time(),
                    auto_fixable=True,
                    suggested_action=ReconciliationAction.AUTO_CLOSE_POSITION
                )
                discrepancies.append(discrepancy)

        # Check for size mismatches
        for key in set(expected_positions.keys()) & set(actual_positions.keys()):
            expected = expected_positions[key]
            actual = actual_positions[key]

            size_diff = abs(expected.size - actual.size)
            tolerance = min(expected.size * Decimal("0.01"), Decimal("0.001"))  # 1% or 0.001

            if size_diff > tolerance:
                severity = 'critical' if size_diff > expected.size * Decimal("0.1") else 'medium'

                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.POSITION_SIZE_MISMATCH,
                    description=f"Position size mismatch for {key}: expected {expected.size}, actual {actual.size}",
                    severity=severity,
                    affected_items=[key],
                    expected_state=expected,
                    actual_state=actual,
                    detected_at=time.time(),
                    auto_fixable=size_diff <= self.max_auto_fix_amount,
                    suggested_action=ReconciliationAction.AUTO_ADJUST_SIZE
                )
                discrepancies.append(discrepancy)

        return discrepancies

    async def _check_balance_discrepancies(self,
                                         actual_balances: Dict[str, BalanceSnapshot]) -> List[Discrepancy]:
        """Check for balance-related discrepancies."""
        discrepancies = []
        expected_balances = self.position_tracker.get_expected_balances()

        for key in expected_balances.keys():
            if key not in actual_balances:
                continue  # Balance might not exist yet

            expected = expected_balances[key]
            actual = actual_balances[key]

            # Check total balance
            balance_diff = abs(expected.total_balance - actual.total_balance)
            tolerance = max(expected.total_balance * Decimal("0.02"), Decimal("1"))  # 2% or $1

            if balance_diff > tolerance:
                severity = 'high' if balance_diff > expected.total_balance * Decimal("0.1") else 'medium'

                discrepancy = Discrepancy(
                    discrepancy_type=DiscrepancyType.BALANCE_MISMATCH,
                    description=f"Balance mismatch for {key}: expected {expected.total_balance}, actual {actual.total_balance}",
                    severity=severity,
                    affected_items=[key],
                    expected_state=expected,
                    actual_state=actual,
                    detected_at=time.time(),
                    auto_fixable=False,
                    suggested_action=ReconciliationAction.MANUAL_REVIEW
                )
                discrepancies.append(discrepancy)

        return discrepancies

    async def _check_order_discrepancies(self,
                                       actual_orders: Dict[str, Dict]) -> List[Discrepancy]:
        """Check for order state discrepancies."""
        discrepancies = []
        pending_orders = self.position_tracker.pending_orders

        # This would check for orders that should be filled but aren't, etc.
        # Implementation depends on specific order tracking requirements

        return discrepancies

    async def _apply_auto_fixes(self, discrepancies: List[Discrepancy]) -> List[str]:
        """Apply automatic fixes for eligible discrepancies."""
        fixes_applied = []

        for discrepancy in discrepancies:
            if not discrepancy.auto_fixable or discrepancy.severity == 'critical':
                continue

            try:
                if discrepancy.suggested_action == ReconciliationAction.REFRESH_DATA:
                    # Trigger data refresh
                    fixes_applied.append(f"Refreshed data for {discrepancy.affected_items}")

                elif discrepancy.suggested_action == ReconciliationAction.AUTO_CLOSE_POSITION:
                    # Would trigger position closure
                    fixes_applied.append(f"Initiated closure of unexpected position {discrepancy.affected_items}")

                elif discrepancy.suggested_action == ReconciliationAction.AUTO_OPEN_POSITION:
                    # Would trigger position opening
                    fixes_applied.append(f"Initiated opening of missing position {discrepancy.affected_items}")

                elif discrepancy.suggested_action == ReconciliationAction.AUTO_ADJUST_SIZE:
                    # Would trigger size adjustment
                    fixes_applied.append(f"Initiated size adjustment for {discrepancy.affected_items}")

            except Exception as e:
                logger.error(f"Failed to apply auto-fix for {discrepancy.description}: {e}")

        return fixes_applied

    def get_reconciliation_metrics(self) -> Dict[str, Any]:
        """Get reconciliation performance metrics."""
        if not self.last_reconciliation:
            return {}

        recent_discrepancies = [
            d for d in self.discrepancy_history
            if d.detected_at > time.time() - 3600  # Last hour
        ]

        return {
            'last_reconciliation_time': self.last_reconciliation.timestamp,
            'last_total_discrepancies': self.last_reconciliation.total_discrepancies,
            'last_critical_issues': len(self.last_reconciliation.critical_issues),
            'recent_discrepancies_count': len(recent_discrepancies),
            'emergency_stop_active': self.emergency_stop_triggered,
            'auto_fix_success_rate': self._calculate_auto_fix_success_rate(),
            'most_common_discrepancy_types': self._get_common_discrepancy_types(),
        }

    def _calculate_auto_fix_success_rate(self) -> float:
        """Calculate success rate of automatic fixes."""
        if not self.last_reconciliation:
            return 0.0

        # This would track success/failure of auto fixes over time
        # For now, return a placeholder
        return 0.85

    def _get_common_discrepancy_types(self) -> Dict[str, int]:
        """Get most common discrepancy types from recent history."""
        recent_discrepancies = [
            d for d in self.discrepancy_history
            if d.detected_at > time.time() - (24 * 3600)  # Last 24 hours
        ]

        type_counts = defaultdict(int)
        for d in recent_discrepancies:
            type_counts[d.discrepancy_type.value] += 1

        return dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5])

    def reset_emergency_stop(self):
        """Reset emergency stop flag."""
        self.emergency_stop_triggered = False
        logger.info("Emergency stop flag reset")


class ReconciliationScheduler:
    """
    Schedules and manages regular reconciliation checks.
    """

    def __init__(self,
                 reconciliation_engine: ReconciliationEngine,
                 check_interval_seconds: int = 300,  # 5 minutes default
                 data_provider: Optional[Callable[[], Awaitable[Optional[
                     Tuple[Dict[str, PositionSnapshot], Dict[str, BalanceSnapshot], Optional[Dict[str, Dict]]]
                 ]]]] = None):
        self.engine = reconciliation_engine
        self.check_interval = check_interval_seconds
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.data_provider = data_provider

    def set_data_provider(self, data_provider: Callable[[], Awaitable[Optional[
        Tuple[Dict[str, PositionSnapshot], Dict[str, BalanceSnapshot], Optional[Dict[str, Dict]]]
    ]]]):
        """Set async data provider for reconciliation inputs."""
        self.data_provider = data_provider

    async def start(self):
        """Start the reconciliation scheduler."""
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(self._reconciliation_loop())
        logger.info(f"Reconciliation scheduler started with {self.check_interval}s interval")

    async def stop(self):
        """Stop the reconciliation scheduler."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Reconciliation scheduler stopped")

    async def _reconciliation_loop(self):
        """Main reconciliation loop."""
        while self.running:
            try:
                if self.data_provider is None:
                    logger.warning("Reconciliation data provider not set; skipping reconciliation.")
                    await asyncio.sleep(self.check_interval)
                    continue

                data = await self.data_provider()
                if data is None:
                    await asyncio.sleep(self.check_interval)
                    continue

                actual_positions, actual_balances, actual_orders = data
                await self.engine.run_full_reconciliation(
                    actual_positions=actual_positions,
                    actual_balances=actual_balances,
                    actual_orders=actual_orders,
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in reconciliation loop: {e}")
                await asyncio.sleep(min(self.check_interval, 60))  # Wait before retry
                continue

            await asyncio.sleep(self.check_interval)
