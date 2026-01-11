"""
Market-specific funding arbitrage strategy with comprehensive risk management.
Integrates all components: edge calculation, scheduling, risk management, reconciliation, and margin monitoring.
"""

import asyncio
import inspect
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import time

from hummingbot.strategy.strategy_py_base import StrategyPyBase
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PositionAction, TradeType, PriceType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.event.events import BuyOrderCompletedEvent, SellOrderCompletedEvent
from hummingbot.logger import HummingbotLogger

from .edge_decomposition import EdgeCalculator, EdgeTracker, EdgeDecomposition
from .funding_scheduler import FundingScheduler, SettlementStatus
from .risk_management import RiskManager, PositionInfo, LiquidityMetrics
from .reconciliation import (
    ReconciliationEngine,
    PositionTracker,
    ReconciliationScheduler,
    PositionSnapshot,
    BalanceSnapshot,
)
from .margin_monitoring import MarginMonitor, MarginInfo, PositionMarginInfo, MarginAction
from .metrics_system import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class FundingArbitrageConfig:
    """Configuration for funding arbitrage strategy."""
    # Entry criteria
    min_edge_required: Decimal = Decimal("0.0005")  # 0.05%
    min_funding_rate_diff: Decimal = Decimal("0.0003")  # 0.03%
    min_position_hold_time_minutes: int = 10

    # Position sizing
    order_amount: Decimal = Decimal("1.0")  # Order amount per position in quote currency

    # Auto trading pair selection
    auto_select_pairs: bool = True  # Automatically select most profitable pairs
    max_trading_pairs: int = 3  # Maximum number of pairs to trade simultaneously
    pair_scan_interval_seconds: int = 300  # How often to rescan pairs (5 min)
    min_pair_volume_24h: Decimal = Decimal("1000000")  # Minimum 24h volume in USD

    # Risk management
    max_notional_per_exchange: Decimal = Decimal("50000")
    max_total_notional: Decimal = Decimal("200000")
    max_leverage: Decimal = Decimal("5")
    max_hedge_gap_percentage: Decimal = Decimal("0.05")  # 5%

    # Timing
    funding_check_interval_seconds: int = 60
    reconciliation_interval_seconds: int = 300  # 5 minutes
    margin_check_interval_seconds: int = 30

    # Safety
    emergency_stop_on_critical_issues: bool = True
    auto_leverage_reduction: bool = True
    auto_position_reconciliation: bool = True


class FundingArbitrageStrategy(StrategyPyBase):
    """
    Advanced funding arbitrage strategy with comprehensive risk management.

    Features:
    - Edge decomposition and transparency
    - Precise funding settlement timing
    - Risk buffers and limits
    - Position/balance reconciliation
    - Margin monitoring and ADL protection
    """

    @classmethod
    def logger(cls) -> HummingbotLogger:
        global logger
        if logger is None:
            logger = logging.getLogger(__name__)
        return logger

    def __init__(self,
                 exchanges: Dict[str, ConnectorBase],
                 config: FundingArbitrageConfig,
                 trading_pairs: List[str]):
        """
        Initialize funding arbitrage strategy.

        Args:
            exchanges: Dict of exchange name -> connector
            config: Strategy configuration
            trading_pairs: List of trading pairs to monitor
        """
        super().__init__()

        self.exchanges = exchanges
        self.config = config
        self.trading_pairs = trading_pairs

        # Initialize components
        self.edge_calculator = EdgeCalculator(min_edge_required=config.min_edge_required)
        self.edge_tracker = EdgeTracker()
        self.funding_scheduler = FundingScheduler()
        self.risk_manager = RiskManager({
            'max_notional_per_exchange': str(config.max_notional_per_exchange),
            'max_total_notional': str(config.max_total_notional),
            'max_leverage': str(config.max_leverage),
            'max_hedge_gap_pct': str(config.max_hedge_gap_percentage),
        })

        # Reconciliation system
        self.position_tracker = PositionTracker()
        self.reconciliation_engine = ReconciliationEngine(
            self.position_tracker,
            auto_fix_enabled=config.auto_position_reconciliation
        )
        self.reconciliation_scheduler = ReconciliationScheduler(
            self.reconciliation_engine,
            config.reconciliation_interval_seconds,
            data_provider=self._collect_reconciliation_data,
        )

        # Margin monitoring
        self.margin_monitor = MarginMonitor(
            max_allowed_leverage=config.max_leverage,
            auto_reduce_enabled=config.auto_leverage_reduction
        )

        # Metrics collection system
        self.metrics = MetricsCollector(
            enable_file_export=True,
            export_interval=300  # Export every 5 minutes
        )

        # Set up metric alerts
        self.metrics.set_alert_threshold("errors_critical_total", "gt", Decimal("5"))
        self.metrics.set_alert_threshold("margin_utilization", "gt", Decimal("80"))
        self.metrics.set_alert_threshold("hedge_gap_max", "gt", Decimal("10"))

        # State tracking
        self.active_positions: Dict[str, Dict] = {}  # position_id -> position_data
        self.funding_rates: Dict[str, Dict[str, FundingInfo]] = {}  # exchange -> pair -> FundingInfo
        self.last_funding_check = 0
        self.emergency_stop_active = False
        self.last_margin_update = 0

        # Auto pair selection
        self.available_pairs: Set[str] = set()  # All available pairs across exchanges
        self.selected_pairs: List[str] = []  # Currently selected pairs for trading
        self.last_pair_scan = 0
        self.pair_profitability: Dict[str, Decimal] = {}  # pair -> estimated profit rate

        # Background tasks tracking (CRITICAL: prevent silent failures)
        self._background_tasks: Set[asyncio.Task] = set()
        self._tick_task: Optional[asyncio.Task] = None

        # Performance tracking
        self.total_funding_collected = Decimal("0")
        self.total_trades_executed = 0
        self.profitable_opportunities_taken = 0
        self.opportunities_skipped_by_reason: Dict[str, int] = {}

        self._setup_callbacks()

        # Validate connectors have required methods
        self._validate_connectors()

    def _validate_connectors(self):
        """
        Validate that all connectors support required methods.
        CRITICAL: Fail early if connector API is incompatible.
        """
        required_methods = ['buy', 'sell']
        recommended_methods = ['get_order', 'get_funding_info']

        for exchange_name, connector in self.exchanges.items():
            # Check required methods
            for method in required_methods:
                if not hasattr(connector, method):
                    raise ValueError(
                        f"Connector {exchange_name} missing REQUIRED method: {method}. "
                        f"Cannot run strategy without this method."
                    )

            # Check recommended methods (warn if missing)
            for method in recommended_methods:
                if not hasattr(connector, method):
                    self.logger().warning(
                        f"Connector {exchange_name} missing recommended method: {method}. "
                        f"Strategy may not work correctly."
                    )

            # Check for in_flight_orders tracker
            if not hasattr(connector, 'in_flight_orders'):
                self.logger().warning(
                    f"Connector {exchange_name} missing 'in_flight_orders' tracker. "
                    f"Order tracking may not work correctly."
                )

            self.logger().info(f"Connector {exchange_name} validation passed")

    def _setup_callbacks(self):
        """Setup callbacks for various components."""
        # Margin monitoring callbacks
        self.margin_monitor.register_action_callback(
            MarginAction.EMERGENCY_EXIT,
            self._handle_emergency_exit
        )
        self.margin_monitor.register_action_callback(
            MarginAction.REDUCE_LEVERAGE,
            self._handle_leverage_reduction
        )

    async def _handle_emergency_exit(self, account_key: str, margin_info: MarginInfo):
        """Handle emergency exit due to margin issues."""
        self.logger().critical(f"Emergency exit triggered for {account_key}")
        self.emergency_stop_active = True

        # Close all positions on the affected exchange
        exchange_name = margin_info.exchange
        await self._close_all_positions_on_exchange(exchange_name)

    async def _handle_leverage_reduction(self, position_id: str, new_leverage: Decimal):
        """
        Handle leverage reduction for a position.

        Args:
            position_id: Position identifier
            new_leverage: Target leverage to reduce to
        """
        if position_id not in self.active_positions:
            self.logger().warning(f"Position {position_id} not found for leverage reduction")
            return

        position_data = self.active_positions[position_id]
        self.logger().warning(f"Reducing leverage for {position_id} to {new_leverage}")

        trading_pair = position_data['trading_pair']
        long_exchange = position_data['long_exchange']
        short_exchange = position_data['short_exchange']
        long_amount_base = position_data.get('long_amount_base', position_data.get('long_amount'))
        short_amount_base = position_data.get('short_amount_base', position_data.get('short_amount'))

        if long_amount_base is None or short_amount_base is None:
            self.logger().error(f"Missing position amounts for {position_id}, cannot reduce leverage")
            return

        long_notional = position_data.get('long_notional')
        short_notional = position_data.get('short_notional')

        if long_notional is None:
            entry_price_long = position_data.get('entry_price_long')
            long_notional = long_amount_base * entry_price_long if entry_price_long else long_amount_base
        if short_notional is None:
            entry_price_short = position_data.get('entry_price_short')
            short_notional = short_amount_base * entry_price_short if entry_price_short else short_amount_base

        # Calculate current leverage
        current_edge = position_data.get('edge_decomposition')
        if not current_edge:
            self.logger().error(f"No edge decomposition found for {position_id}, cannot reduce leverage")
            return

        current_leverage_long = current_edge.leverage_long
        current_leverage_short = current_edge.leverage_short

        # Determine which position needs reduction
        needs_long_reduction = current_leverage_long > new_leverage
        needs_short_reduction = current_leverage_short > new_leverage

        if not needs_long_reduction and not needs_short_reduction:
            self.logger().info(f"Position {position_id} already at target leverage {new_leverage}")
            return

        # Strategy: Partially close positions to reduce effective leverage
        # Formula: new_size = current_size * (new_leverage / current_leverage)

        long_connector = self.exchanges.get(long_exchange)
        short_connector = self.exchanges.get(short_exchange)

        if not long_connector or not short_connector:
            self.logger().error(f"Connectors not found for {position_id}, manual intervention required")
            return

        try:
            close_tasks = []

            if needs_long_reduction:
                # Calculate how much to reduce long position
                reduction_ratio = (current_leverage_long - new_leverage) / current_leverage_long
                reduce_amount_long = long_amount_base * reduction_ratio

                self.logger().info(
                    f"Reducing long position on {long_exchange} by {reduce_amount_long} "
                    f"({reduction_ratio:.2%}) to reduce leverage from {current_leverage_long} to {new_leverage}"
                )

                # Close partial long position (sell)
                close_tasks.append(
                    self._place_order(
                        connector=long_connector,
                        trading_pair=trading_pair,
                        is_buy=False,  # SELL to reduce long
                        amount=reduce_amount_long,
                        position_action=PositionAction.CLOSE
                    )
                )

                # Update tracked amount
                position_data['long_amount_base'] = long_amount_base - reduce_amount_long
                position_data['long_notional'] = long_notional * (Decimal('1') - reduction_ratio)

            if needs_short_reduction:
                # Calculate how much to reduce short position
                reduction_ratio = (current_leverage_short - new_leverage) / current_leverage_short
                reduce_amount_short = short_amount_base * reduction_ratio

                self.logger().info(
                    f"Reducing short position on {short_exchange} by {reduce_amount_short} "
                    f"({reduction_ratio:.2%}) to reduce leverage from {current_leverage_short} to {new_leverage}"
                )

                # Close partial short position (buy)
                close_tasks.append(
                    self._place_order(
                        connector=short_connector,
                        trading_pair=trading_pair,
                        is_buy=True,  # BUY to reduce short
                        amount=reduce_amount_short,
                        position_action=PositionAction.CLOSE
                    )
                )

                # Update tracked amount
                position_data['short_amount_base'] = short_amount_base - reduce_amount_short
                position_data['short_notional'] = short_notional * (Decimal('1') - reduction_ratio)

            # Execute reductions in parallel
            if close_tasks:
                results = await asyncio.gather(*close_tasks, return_exceptions=True)

                # Check for failures
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        side = "long" if i == 0 else "short"
                        self.logger().error(f"Failed to reduce {side} position for {position_id}: {result}")
                        # NOTE: In production, this requires manual intervention
                        # The position is now unbalanced and needs immediate attention
                        self.logger().critical(
                            f"MANUAL INTERVENTION REQUIRED: Position {position_id} {side} reduction failed! "
                            f"Position may be unbalanced."
                        )
                    else:
                        order_id = result
                        self.logger().info(f"Leverage reduction order placed: {order_id}")

            # Update risk manager with new position sizes
            if needs_long_reduction:
                self.risk_manager.update_position_notional(
                    long_exchange, trading_pair, position_data['long_notional']
                )
            if needs_short_reduction:
                self.risk_manager.update_position_notional(
                    short_exchange, trading_pair, position_data['short_notional']
                )

            self.logger().info(f"Leverage reduction completed for {position_id}")

        except Exception as e:
            self.logger().error(f"Failed to reduce leverage for {position_id}: {e}")
            self.logger().critical(
                f"MANUAL INTERVENTION REQUIRED: Leverage reduction for {position_id} failed! "
                f"Position may be at risk."
            )

    async def _close_all_positions_on_exchange(self, exchange_name: str):
        """Close all active positions on a specific exchange."""
        positions_to_close = [
            pos_id for pos_id, pos_data in self.active_positions.items()
            if exchange_name in (pos_data.get('long_exchange'), pos_data.get('short_exchange'))
        ]

        for position_id in positions_to_close:
            await self._close_position(position_id, "Emergency exit")

    def tick(self, timestamp: float):
        """
        Main strategy tick - called every second by hummingbot.

        Args:
            timestamp: Current timestamp from hummingbot clock
        """
        if self._tick_task is None or self._tick_task.done():
            self._tick_task = asyncio.create_task(self.on_tick())
        else:
            self.logger().debug("Skipping tick because previous tick is still running")

    async def on_tick(self):
        """Main strategy tick - called periodically."""
        try:
            current_time = time.time()

            # Auto pair selection - scan for profitable pairs
            if self.config.auto_select_pairs:
                if current_time - self.last_pair_scan >= self.config.pair_scan_interval_seconds:
                    await self._scan_and_select_pairs()
                    self.last_pair_scan = current_time

            # Update funding rates for active/selected pairs
            if current_time - self.last_funding_check >= self.config.funding_check_interval_seconds:
                await self._update_funding_rates()
                self.last_funding_check = current_time

            # Check for arbitrage opportunities
            if not self.emergency_stop_active:
                await self._check_arbitrage_opportunities()

            # Update margin monitoring snapshots
            if current_time - self.last_margin_update >= self.config.margin_check_interval_seconds:
                await self._update_margin_monitoring()
                self.last_margin_update = current_time

            # Monitor existing positions
            await self._monitor_existing_positions()

        except Exception as e:
            self.logger().error(f"Error in strategy tick: {e}")

    async def _scan_and_select_pairs(self):
        """
        Scan all available pairs across exchanges and select the most profitable ones.
        Updates self.selected_pairs with top pairs by funding rate differential.
        """
        self.logger().info(" Scanning trading pairs for best funding rate opportunities...")

        try:
            # Collect all available pairs from all exchanges
            all_pairs: Set[str] = set()
            pair_data: Dict[str, Dict] = {}  # pair -> {exchange -> funding_info, volume}

            for exchange_name, connector in self.exchanges.items():
                try:
                    # Get all trading pairs for this exchange
                    if hasattr(connector, 'trading_pairs'):
                        exchange_pairs = connector.trading_pairs
                    elif hasattr(connector, 'get_trading_pairs'):
                        exchange_pairs = await connector.get_trading_pairs()
                    else:
                        # Fallback: use predefined list or skip
                        continue

                    for pair in exchange_pairs:
                        all_pairs.add(pair)

                        # Get funding info
                        funding_info = await self._get_funding_info(connector, pair)
                        if funding_info:
                            if pair not in pair_data:
                                pair_data[pair] = {}
                            volume_24h = await self._get_24h_volume(connector, pair)
                            pair_data[pair][exchange_name] = {
                                'funding_info': funding_info,
                                'rate': Decimal(str(funding_info.rate)) if hasattr(funding_info, 'rate') else Decimal('0'),
                                'volume_24h': volume_24h,
                            }

                except Exception as e:
                    self.logger().warning(f"Failed to scan pairs on {exchange_name}: {e}")

            # Calculate profitability for each pair
            profitability_scores: Dict[str, Decimal] = {}

            for pair, exchanges_data in pair_data.items():
                if len(exchanges_data) < 2:
                    continue  # Need at least 2 exchanges for arbitrage

                # Find max and min funding rates
                rates = [data['rate'] for data in exchanges_data.values()]
                if not rates:
                    continue

                max_rate = max(rates)
                min_rate = min(rates)
                rate_diff = abs(max_rate - min_rate)

                volumes = [data.get('volume_24h') for data in exchanges_data.values() if data.get('volume_24h') is not None]
                if volumes:
                    min_volume = min(volumes)
                    if min_volume < self.config.min_pair_volume_24h:
                        continue

                # Check if meets minimum criteria
                if rate_diff >= self.config.min_funding_rate_diff:
                    # Profitability score = rate difference (simple for now)
                    profitability_scores[pair] = rate_diff

            # Select top N pairs
            if profitability_scores:
                sorted_pairs = sorted(
                    profitability_scores.items(),
                    key=lambda x: x[1],
                    reverse=True
                )

                # Update selected pairs
                new_selected = [pair for pair, score in sorted_pairs[:self.config.max_trading_pairs]]

                if new_selected != self.selected_pairs:
                    self.logger().info(
                        f" Updated selected pairs:\n" +
                        "\n".join([
                            f"  {i+1}. {pair}: {profitability_scores[pair]:.4%} rate differential"
                            for i, pair in enumerate(new_selected)
                        ])
                    )
                    self.selected_pairs = new_selected
                    self.pair_profitability = profitability_scores

                    # Update trading_pairs to use selected pairs
                    if self.config.auto_select_pairs:
                        self.trading_pairs = self.selected_pairs
            else:
                self.logger().warning("No profitable pairs found meeting minimum criteria")

        except Exception as e:
            self.logger().error(f"Error scanning pairs: {e}")

    async def _update_funding_rates(self):
        """Update funding rates from all exchanges."""
        for exchange_name, connector in self.exchanges.items():
            try:
                for trading_pair in self.trading_pairs:
                    funding_info = await self._get_funding_info(connector, trading_pair)
                    if funding_info:
                        if exchange_name not in self.funding_rates:
                            self.funding_rates[exchange_name] = {}
                        self.funding_rates[exchange_name][trading_pair] = funding_info

            except Exception as e:
                self.logger().warning(f"Failed to update funding rates for {exchange_name}: {e}")

    async def _check_arbitrage_opportunities(self):
        """Check for profitable arbitrage opportunities."""
        for trading_pair in self.trading_pairs:
            # Get funding rates for this pair across exchanges
            pair_funding_rates = {}
            for exchange_name, rates in self.funding_rates.items():
                if trading_pair in rates:
                    pair_funding_rates[exchange_name] = rates[trading_pair]

            if len(pair_funding_rates) < 2:
                continue  # Need at least 2 exchanges

            # Find best arbitrage opportunity
            best_opportunity = await self._find_best_opportunity(trading_pair, pair_funding_rates)

            if best_opportunity:
                await self._evaluate_and_execute_opportunity(best_opportunity)

    async def _find_best_opportunity(self,
                                   trading_pair: str,
                                   funding_rates: Dict[str, FundingInfo]) -> Optional[Dict]:
        """Find the best arbitrage opportunity for a trading pair."""
        best_opportunity = None
        best_edge = Decimal("-1")

        # Check all exchange pairs
        exchange_names = list(funding_rates.keys())
        for i, long_exchange in enumerate(exchange_names):
            for short_exchange in exchange_names[i+1:]:
                # Calculate both directions
                opportunities = [
                    (long_exchange, short_exchange),
                    (short_exchange, long_exchange)
                ]

                for long_ex, short_ex in opportunities:
                    long_rate = funding_rates[long_ex].rate
                    short_rate = funding_rates[short_ex].rate

                    # Skip if funding rate difference is too small
                    rate_diff = short_rate - long_rate

                    # CRITICAL: Validate funding diff is POSITIVE
                    # We must RECEIVE more on short than we PAY on long
                    if rate_diff <= 0:
                        # Skip opportunities where we would LOSE money on funding
                        self.opportunities_skipped_by_reason['negative_funding'] = \
                            self.opportunities_skipped_by_reason.get('negative_funding', 0) + 1
                        continue

                    if rate_diff < self.config.min_funding_rate_diff:
                        self.opportunities_skipped_by_reason['funding_diff_too_small'] = \
                            self.opportunities_skipped_by_reason.get('funding_diff_too_small', 0) + 1
                        continue

                    # Calculate edge decomposition
                    edge = await self._calculate_opportunity_edge(
                        trading_pair, long_ex, short_ex, long_rate, short_rate
                    )

                    if edge and edge.is_profitable and edge.total_edge > best_edge:
                        best_edge = edge.total_edge
                        best_opportunity = {
                            'trading_pair': trading_pair,
                            'long_exchange': long_ex,
                            'short_exchange': short_ex,
                            'edge_decomposition': edge,
                            'funding_rates': {
                                'long': long_rate,
                                'short': short_rate
                            }
                        }

        return best_opportunity

    async def _get_borrow_rates(self, trading_pair: str, exchanges: List[str]) -> Dict[str, Decimal]:
        """
        Get borrow rates for assets from exchanges.

        Args:
            trading_pair: Trading pair to get borrow rates for
            exchanges: List of exchanges to check

        Returns:
            Dict of asset -> borrow rate (annualized)
        """
        borrow_rates = {}

        # Parse trading pair to get base and quote assets
        if '-' in trading_pair:
            base_asset, quote_asset = trading_pair.split('-', 1)
        else:
            # Parse trading pair format like BTCUSDT, ETHUSDC, etc.
            if trading_pair.endswith(('USDT', 'USDC', 'BUSD', 'TUSD')):
                base_asset = trading_pair[:-4]
                quote_asset = trading_pair[-4:]
            elif trading_pair.endswith(('USD', 'EUR', 'GBP', 'JPY', 'BTC', 'ETH', 'BNB', 'DAI')):
                base_asset = trading_pair[:-3]
                quote_asset = trading_pair[-3:]
            else:
                base_asset = trading_pair[:-3] if len(trading_pair) > 3 else ''
                quote_asset = trading_pair[-3:] if len(trading_pair) > 3 else trading_pair

        # Try to get real borrow rates from connectors
        for asset in [base_asset, quote_asset]:
            rates_found = []

            for exchange_name in exchanges:
                connector = self.exchanges.get(exchange_name)
                if not connector:
                    continue

                try:
                    # Try multiple methods connectors might use for borrow rates
                    borrow_rate = None

                    # Method 1: get_borrow_rate method
                    if hasattr(connector, 'get_borrow_rate'):
                        try:
                            borrow_rate = await connector.get_borrow_rate(asset)
                        except Exception:
                            pass

                    # Method 2: get_funding_payment method (some exchanges combine this)
                    if borrow_rate is None and hasattr(connector, 'get_funding_payment'):
                        try:
                            funding_payment = await connector.get_funding_payment(trading_pair)
                            if funding_payment and hasattr(funding_payment, 'borrow_rate'):
                                borrow_rate = funding_payment.borrow_rate
                        except Exception:
                            pass

                    # Method 3: Check connector's fee/rate configuration
                    if borrow_rate is None and hasattr(connector, 'borrow_rates'):
                        try:
                            borrow_rate = connector.borrow_rates.get(asset)
                        except Exception:
                            pass

                    if borrow_rate is not None:
                        rates_found.append(Decimal(str(borrow_rate)))

                except Exception as e:
                    self.logger().debug(f"Failed to get borrow rate for {asset} from {exchange_name}: {e}")
                    continue

            # Use average of found rates, or default
            if rates_found:
                borrow_rates[asset] = sum(rates_found) / Decimal(len(rates_found))
                self.logger().debug(f"Using average borrow rate for {asset}: {borrow_rates[asset]:.6f}")
            else:
                # Use reasonable defaults based on asset type
                if asset in ['USD', 'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI']:
                    default_rate = Decimal("0.00005")  # 0.005% per 8h = ~5% APR
                elif asset in ['BTC', 'ETH']:
                    default_rate = Decimal("0.0001")   # 0.01% per 8h = ~10% APR
                else:
                    default_rate = Decimal("0.00015")  # 0.015% per 8h = ~15% APR for altcoins

                borrow_rates[asset] = default_rate
                self.logger().debug(f"Using default borrow rate for {asset}: {default_rate:.6f}")

        return borrow_rates

    async def _get_slippage_estimates(
        self,
        trading_pair: str,
        exchanges: List[str],
        notional_amount: Decimal
    ) -> Dict[str, Decimal]:
        """
        Get slippage estimates based on order book depth.

        Args:
            trading_pair: Trading pair to estimate slippage for
            exchanges: List of exchanges to check
            notional_amount: Planned trade size

        Returns:
            Dict of exchange -> estimated slippage percentage
        """
        slippage_estimates = {}

        for exchange_name in exchanges:
            connector = self.exchanges.get(exchange_name)
            if not connector:
                # Use conservative default if connector not found
                slippage_estimates[exchange_name] = Decimal("0.001")  # 0.1%
                continue

            try:
                # Get order book liquidity
                liquidity = await self._get_order_book_liquidity(connector, trading_pair)

                if not liquidity:
                    # No liquidity data - use conservative estimate
                    slippage_estimates[exchange_name] = Decimal("0.001")  # 0.1%
                    self.logger().debug(
                        f"No liquidity data for {exchange_name}/{trading_pair}, "
                        f"using default slippage estimate: 0.1%"
                    )
                    continue

                # Calculate slippage based on:
                # 1. Spread (immediate cost)
                # 2. Market depth (price impact for notional amount)

                # Base slippage from spread
                spread_slippage = liquidity.avg_spread_bps / Decimal("10000") / Decimal("2")  # Half spread

                # Depth-based slippage
                # Compare notional amount to available liquidity
                available_liquidity = min(liquidity.bid_depth_1pct, liquidity.ask_depth_1pct)

                if available_liquidity > 0:
                    # Calculate impact ratio
                    impact_ratio = notional_amount / available_liquidity

                    # Progressive slippage model:
                    # - Up to 10% of liquidity: minimal additional slippage
                    # - 10-50% of liquidity: linear additional slippage
                    # - > 50% of liquidity: exponential additional slippage
                    if impact_ratio <= Decimal("0.1"):
                        depth_slippage = impact_ratio * Decimal("0.0001")  # Very small
                    elif impact_ratio <= Decimal("0.5"):
                        depth_slippage = Decimal("0.00001") + (impact_ratio - Decimal("0.1")) * Decimal("0.0005")
                    else:
                        # Exponential for large trades
                        depth_slippage = Decimal("0.0002") + (impact_ratio - Decimal("0.5")) * Decimal("0.002")
                else:
                    # No liquidity - very high slippage expected
                    depth_slippage = Decimal("0.005")  # 0.5%

                # Total estimated slippage
                total_slippage = spread_slippage + depth_slippage

                # Cap slippage at reasonable max (2%)
                total_slippage = min(total_slippage, Decimal("0.02"))

                slippage_estimates[exchange_name] = total_slippage

                self.logger().debug(
                    f"Slippage estimate for {exchange_name}/{trading_pair}: "
                    f"{total_slippage:.4%} (spread={spread_slippage:.4%}, depth={depth_slippage:.4%})"
                )

            except Exception as e:
                self.logger().warning(f"Failed to estimate slippage for {exchange_name}: {e}")
                # Fallback to conservative default
                slippage_estimates[exchange_name] = Decimal("0.001")  # 0.1%

        return slippage_estimates

    async def _calculate_opportunity_edge(self,
                                        trading_pair: str,
                                        long_exchange: str,
                                        short_exchange: str,
                                        long_rate: Decimal,
                                        short_rate: Decimal) -> Optional[EdgeDecomposition]:
        """Calculate detailed edge decomposition for an opportunity."""
        # Determine position size based on risk limits
        notional_amount = await self._calculate_position_size(trading_pair, long_exchange, short_exchange)

        if notional_amount <= 0:
            return None

        # Get REAL fee configuration from connectors
        # CRITICAL FIX: Use actual exchange fees instead of hardcoded values
        fees_config = {}
        for exchange_name, order_side in [
            (long_exchange, TradeType.BUY),
            (short_exchange, TradeType.SELL),
        ]:
            connector = self.exchanges.get(exchange_name)
            if connector:
                # Get real fees from connector
                maker_fee = Decimal("0.0002")  # Default fallback
                taker_fee = Decimal("0.0005")  # Default fallback

                fee_rates = self._get_fee_rates(
                    connector=connector,
                    trading_pair=trading_pair,
                    notional_amount=notional_amount,
                    order_side=order_side,
                    fallback_maker=maker_fee,
                    fallback_taker=taker_fee,
                )
                maker_fee, taker_fee = fee_rates

                # Alternative: Check for trading_fees attribute
                if hasattr(connector, 'trading_fees'):
                    try:
                        trading_fees = connector.trading_fees
                        if trading_pair in trading_fees:
                            fee_tier = trading_fees[trading_pair]
                            maker_fee = Decimal(str(fee_tier.get('maker', maker_fee)))
                            taker_fee = Decimal(str(fee_tier.get('taker', taker_fee)))
                    except Exception:
                        pass

                fees_config[exchange_name] = {'maker': maker_fee, 'taker': taker_fee}
                self.logger().debug(f"Using fees for {exchange_name}: maker={maker_fee:.4%}, taker={taker_fee:.4%}")
            else:
                # Fallback to defaults if connector not found
                fees_config[exchange_name] = {'maker': Decimal("0.0002"), 'taker': Decimal("0.0005")}

        # Get borrow rates from exchanges (with fallback to defaults)
        borrow_rates = await self._get_borrow_rates(trading_pair, [long_exchange, short_exchange])

        # Get slippage estimates based on order book depth
        slippage_estimates = await self._get_slippage_estimates(
            trading_pair, [long_exchange, short_exchange], notional_amount
        )

        # Calculate edge
        edge = self.edge_calculator.calculate_edge(
            trading_pair=trading_pair,
            exchange_long=long_exchange,
            exchange_short=short_exchange,
            funding_rate_long=long_rate,
            funding_rate_short=short_rate,
            notional_amount=notional_amount,
            fees_config=fees_config,
            borrow_rates=borrow_rates,
            slippage_estimates=slippage_estimates,
            funding_period_hours_long=self._get_funding_period_hours(long_exchange),
            funding_period_hours_short=self._get_funding_period_hours(short_exchange),
        )

        # Track the calculation
        self.edge_tracker.add_edge_calculation(edge)

        return edge

    async def _get_order_book_liquidity(
        self,
        connector: ConnectorBase,
        trading_pair: str
    ) -> Optional[LiquidityMetrics]:
        """
        Get real-time liquidity metrics from connector's order book.

        This checks if there are limit orders in the order book that we can
        take immediately with market orders.

        Args:
            connector: Exchange connector
            trading_pair: Trading pair to check

        Returns:
            LiquidityMetrics if successful, None otherwise
        """
        try:
            # Get order book from connector
            order_book = None

            if hasattr(connector, 'get_order_book'):
                order_book = connector.get_order_book(trading_pair)
            elif hasattr(connector, 'order_book_tracker') and hasattr(connector.order_book_tracker, 'get_order_book'):
                order_book = connector.order_book_tracker.get_order_book(trading_pair)

            if not order_book:
                self.logger().warning(f"No order book available for {connector.name}/{trading_pair}")
                return None

            # Get best bid and ask
            try:
                best_bid = order_book.get_price(False)  # False = bid
                best_ask = order_book.get_price(True)   # True = ask
            except Exception:
                # Alternative method
                if hasattr(order_book, 'snapshot'):
                    snapshot = order_book.snapshot
                    if len(snapshot[0]) > 0 and len(snapshot[1]) > 0:  # bids, asks
                        best_bid = Decimal(str(snapshot[0][0][0]))  # First bid price
                        best_ask = Decimal(str(snapshot[1][0][0]))  # First ask price
                    else:
                        self.logger().warning(f"Empty order book for {connector.name}/{trading_pair}")
                        return None
                else:
                    self.logger().warning(f"Cannot get prices from order book for {connector.name}/{trading_pair}")
                    return None

            if best_bid <= 0 or best_ask <= 0:
                self.logger().warning(f"Invalid prices in order book: bid={best_bid}, ask={best_ask}")
                return None

            # Calculate mid price
            mid_price = (best_bid + best_ask) / Decimal("2")

            # Calculate price ranges for depth analysis
            one_pct_range = mid_price * Decimal("0.01")  # 1% from mid
            five_pct_range = mid_price * Decimal("0.05")  # 5% from mid

            # Calculate bid depth (liquidity for selling/shorting)
            bid_price_1pct = mid_price - one_pct_range
            bid_price_5pct = mid_price - five_pct_range

            # Calculate ask depth (liquidity for buying/longing)
            ask_price_1pct = mid_price + one_pct_range
            ask_price_5pct = mid_price + five_pct_range

            # Get volume within ranges
            # For perpetuals, we use notional value (price * quantity)
            bid_depth_1pct = Decimal("0")
            bid_depth_5pct = Decimal("0")
            ask_depth_1pct = Decimal("0")
            ask_depth_5pct = Decimal("0")

            try:
                # Try to get depth from order book methods
                if hasattr(order_book, 'get_volume_for_price'):
                    bid_depth_1pct = order_book.get_volume_for_price(False, bid_price_1pct)
                    bid_depth_5pct = order_book.get_volume_for_price(False, bid_price_5pct)
                    ask_depth_1pct = order_book.get_volume_for_price(True, ask_price_1pct)
                    ask_depth_5pct = order_book.get_volume_for_price(True, ask_price_5pct)
                elif hasattr(order_book, 'snapshot'):
                    # Manual calculation from snapshot
                    snapshot = order_book.snapshot
                    bids = snapshot[0]  # List of [price, quantity]
                    asks = snapshot[1]

                    # Calculate bid depth
                    for price, qty in bids:
                        price_dec = Decimal(str(price))
                        qty_dec = Decimal(str(qty))
                        notional = price_dec * qty_dec

                        if price_dec >= bid_price_1pct:
                            bid_depth_1pct += notional
                        if price_dec >= bid_price_5pct:
                            bid_depth_5pct += notional

                    # Calculate ask depth
                    for price, qty in asks:
                        price_dec = Decimal(str(price))
                        qty_dec = Decimal(str(qty))
                        notional = price_dec * qty_dec

                        if price_dec <= ask_price_1pct:
                            ask_depth_1pct += notional
                        if price_dec <= ask_price_5pct:
                            ask_depth_5pct += notional

            except Exception as e:
                self.logger().warning(f"Error calculating order book depth: {e}")
                # Use conservative estimates based on spread
                spread = best_ask - best_bid
                avg_price = mid_price
                # Estimate: assume some minimal liquidity
                bid_depth_1pct = avg_price * Decimal("10")  # ~10 units
                bid_depth_5pct = avg_price * Decimal("50")  # ~50 units
                ask_depth_1pct = avg_price * Decimal("10")
                ask_depth_5pct = avg_price * Decimal("50")

            # Calculate spread in basis points
            spread = best_ask - best_bid
            spread_bps = (spread / mid_price) * Decimal("10000")

            # Calculate impact score (simplified)
            # This estimates the price impact of a $1000 order
            reference_size = Decimal("1000")
            available_liquidity = min(bid_depth_1pct, ask_depth_1pct)

            if available_liquidity > 0:
                impact_score = min((reference_size / available_liquidity) * Decimal("2"), Decimal("1.0"))
            else:
                impact_score = Decimal("1.0")  # Maximum impact if no liquidity

            liquidity_metrics = LiquidityMetrics(
                exchange=connector.name,
                trading_pair=trading_pair,
                bid_depth_1pct=bid_depth_1pct,
                ask_depth_1pct=ask_depth_1pct,
                bid_depth_5pct=bid_depth_5pct,
                ask_depth_5pct=ask_depth_5pct,
                avg_spread_bps=spread_bps,
                impact_score=impact_score,
                timestamp=time.time()
            )

            self.logger().debug(
                f"Order book liquidity for {connector.name}/{trading_pair}: "
                f"bid_1%={bid_depth_1pct:.2f}, ask_1%={ask_depth_1pct:.2f}, "
                f"spread={spread_bps:.2f}bps"
            )

            return liquidity_metrics

        except Exception as e:
            self.logger().error(f"Failed to get order book liquidity for {connector.name}/{trading_pair}: {e}")
            import traceback
            self.logger().debug(traceback.format_exc())
            return None

    async def _get_24h_volume(self, connector: ConnectorBase, trading_pair: str) -> Optional[Decimal]:
        """Best-effort 24h quote volume fetch for pair selection."""
        name = getattr(connector, 'name', str(connector))
        try:
            volume = None
            if hasattr(connector, 'get_24h_volume'):
                volume = connector.get_24h_volume(trading_pair)
            elif hasattr(connector, 'get_trading_pair_24h_volume'):
                volume = connector.get_trading_pair_24h_volume(trading_pair)
            elif hasattr(connector, 'get_ticker'):
                ticker = connector.get_ticker(trading_pair)
                if asyncio.iscoroutine(ticker):
                    ticker = await ticker
                if isinstance(ticker, dict):
                    for key in ('quote_volume', 'quoteVolume', 'volume', 'base_volume', 'baseVolume'):
                        if key in ticker and ticker[key] is not None:
                            volume = ticker[key]
                            break
                else:
                    for key in ('quote_volume', 'quoteVolume', 'volume', 'base_volume', 'baseVolume'):
                        if hasattr(ticker, key):
                            volume = getattr(ticker, key)
                            break

            if volume is None:
                return None

            volume_dec = Decimal(str(volume))
            if volume_dec <= 0:
                return None

            return volume_dec

        except Exception as e:
            self.logger().debug(f"Failed to get 24h volume for {name}/{trading_pair}: {e}")
            return None

    def _get_mid_price(self, connector: ConnectorBase, trading_pair: str) -> Optional[Decimal]:
        """Get mid price with fallbacks for different connector implementations."""
        name = getattr(connector, 'name', str(connector))
        try:
            price = None
            if hasattr(connector, 'get_mid_price'):
                price = connector.get_mid_price(trading_pair)
            elif hasattr(connector, 'get_price_by_type'):
                price = connector.get_price_by_type(trading_pair, PriceType.MidPrice)
            else:
                order_book = None
                if hasattr(connector, 'get_order_book'):
                    order_book = connector.get_order_book(trading_pair)
                elif hasattr(connector, 'order_book_tracker') and hasattr(connector.order_book_tracker, 'get_order_book'):
                    order_book = connector.order_book_tracker.get_order_book(trading_pair)
                if order_book:
                    try:
                        best_bid = order_book.get_price(False)
                        best_ask = order_book.get_price(True)
                        if best_bid is not None and best_ask is not None:
                            price = (Decimal(str(best_bid)) + Decimal(str(best_ask))) / Decimal('2')
                    except Exception:
                        price = None

            if price is None:
                self.logger().warning(f"Mid price unavailable for {name}/{trading_pair}")
                return None

            price_dec = Decimal(str(price))
            if price_dec <= 0:
                self.logger().warning(f"Invalid mid price for {name}/{trading_pair}: {price_dec}")
                return None

            return price_dec

        except Exception as e:
            self.logger().warning(f"Failed to get mid price for {name}/{trading_pair}: {e}")
            return None

    async def _get_funding_info(self, connector: ConnectorBase, trading_pair: str) -> Optional[FundingInfo]:
        """Fetch funding info from connector with sync/async compatibility."""
        if not hasattr(connector, 'get_funding_info'):
            return None
        name = getattr(connector, 'name', str(connector))
        try:
            funding_info = connector.get_funding_info(trading_pair)
            if inspect.isawaitable(funding_info):
                funding_info = await funding_info
            return funding_info
        except Exception as e:
            self.logger().warning(f"Failed to fetch funding info for {name}/{trading_pair}: {e}")
            return None

    def _split_trading_pair(self, connector: ConnectorBase, trading_pair: str) -> Tuple[str, str]:
        """Split trading pair into base and quote with connector fallback."""
        if hasattr(connector, 'split_trading_pair'):
            try:
                return connector.split_trading_pair(trading_pair)
            except Exception:
                pass

        if '-' in trading_pair:
            return trading_pair.split('-', 1)

        if trading_pair.endswith(('USDT', 'USDC', 'BUSD', 'TUSD')):
            return trading_pair[:-4], trading_pair[-4:]
        if trading_pair.endswith(('USD', 'EUR', 'GBP', 'JPY', 'BTC', 'ETH', 'BNB', 'DAI')):
            return trading_pair[:-3], trading_pair[-3:]

        return trading_pair[:-3], trading_pair[-3:]

    def _get_fee_percent(self,
                         connector: ConnectorBase,
                         base: str,
                         quote: str,
                         order_type: OrderType,
                         order_side: TradeType,
                         amount: Decimal,
                         price: Decimal,
                         is_maker: bool) -> Optional[Decimal]:
        """Return fee percent for a specific order shape."""
        fee_info = None
        try:
            fee_info = connector.get_fee(
                base, quote, order_type, order_side, PositionAction.OPEN, amount, price, is_maker
            )
        except TypeError:
            try:
                fee_info = connector.get_fee(
                    base, quote, order_type, order_side, amount, price, is_maker
                )
            except TypeError:
                try:
                    fee_info = connector.get_fee(base, quote, order_type, order_side, amount, price)
                except Exception:
                    return None
        except Exception:
            return None

        if fee_info is None:
            return None

        if hasattr(fee_info, 'percent'):
            return Decimal(str(fee_info.percent))

        if hasattr(fee_info, 'maker_percent_fee_decimal') or hasattr(fee_info, 'taker_percent_fee_decimal'):
            if is_maker and hasattr(fee_info, 'maker_percent_fee_decimal'):
                return Decimal(str(fee_info.maker_percent_fee_decimal))
            if not is_maker and hasattr(fee_info, 'taker_percent_fee_decimal'):
                return Decimal(str(fee_info.taker_percent_fee_decimal))

        if isinstance(fee_info, dict):
            key = 'maker' if is_maker else 'taker'
            if key in fee_info:
                return Decimal(str(fee_info[key]))

        return None

    def _get_fee_rates(self,
                       connector: ConnectorBase,
                       trading_pair: str,
                       notional_amount: Decimal,
                       order_side: TradeType,
                       fallback_maker: Decimal,
                       fallback_taker: Decimal) -> Tuple[Decimal, Decimal]:
        """Get maker/taker fee rates with fallback to defaults."""
        price = self._get_mid_price(connector, trading_pair)
        if price is None or price <= 0:
            return fallback_maker, fallback_taker

        base, quote = self._split_trading_pair(connector, trading_pair)
        base_amount = notional_amount / price

        maker_fee = self._get_fee_percent(
            connector, base, quote, OrderType.LIMIT, order_side, base_amount, price, True
        )
        taker_fee = self._get_fee_percent(
            connector, base, quote, OrderType.MARKET, order_side, base_amount, price, False
        )

        return (
            maker_fee if maker_fee is not None else fallback_maker,
            taker_fee if taker_fee is not None else fallback_taker,
        )

    def _get_funding_period_hours(self, exchange_name: str) -> Decimal:
        """Infer funding period length from scheduler settings."""
        schedule = self.funding_scheduler.exchange_schedules.get(exchange_name.lower())
        if not schedule or not schedule.settlement_times:
            return Decimal("8")

        periods = len(schedule.settlement_times)
        if periods <= 0:
            return Decimal("8")

        return Decimal("24") / Decimal(str(periods))

    def _get_connector_positions(self, connector: ConnectorBase) -> Optional[List]:
        """Best-effort position fetch for reconciliation/margin monitoring."""
        try:
            if hasattr(connector, 'account_positions'):
                return list(connector.account_positions.values())
            if hasattr(connector, 'get_position'):
                positions = []
                for trading_pair in self.trading_pairs:
                    try:
                        position = connector.get_position(trading_pair)
                        if position is not None:
                            positions.append(position)
                    except Exception:
                        continue
                return positions
        except Exception:
            return None
        return None

    def _get_connector_balances(self, connector: ConnectorBase) -> Optional[Dict[str, Decimal]]:
        """Best-effort balances fetch for reconciliation."""
        if hasattr(connector, 'get_all_balances'):
            try:
                return connector.get_all_balances()
            except Exception:
                return None
        return None

    def _get_available_balance(self, connector: ConnectorBase, asset: str) -> Decimal:
        """Best-effort available balance fetch."""
        if hasattr(connector, 'get_available_balance'):
            try:
                return Decimal(str(connector.get_available_balance(asset)))
            except Exception:
                return Decimal("0")
        if hasattr(connector, 'get_balance'):
            try:
                return Decimal(str(connector.get_balance(asset)))
            except Exception:
                return Decimal("0")
        return Decimal("0")

    def _get_total_balance(self, connector: ConnectorBase, asset: str) -> Decimal:
        """Best-effort total balance fetch."""
        if hasattr(connector, 'get_balance'):
            try:
                return Decimal(str(connector.get_balance(asset)))
            except Exception:
                return Decimal("0")

        balances = self._get_connector_balances(connector)
        if balances and asset in balances:
            try:
                return Decimal(str(balances[asset]))
            except Exception:
                return Decimal("0")

        return Decimal("0")

    def _build_position_snapshot(self,
                                 exchange: str,
                                 trading_pair: str,
                                 side: str,
                                 size: Decimal,
                                 entry_price: Decimal,
                                 leverage: Decimal,
                                 unrealized_pnl: Decimal,
                                 mark_price: Optional[Decimal]) -> PositionSnapshot:
        """Create a reconciliation snapshot from position values."""
        notional_value = abs(size) * entry_price
        margin_used = notional_value / leverage if leverage > 0 else notional_value
        if mark_price is None:
            mark_price = entry_price
        return PositionSnapshot(
            exchange=exchange,
            trading_pair=trading_pair,
            side=side,
            size=size,
            notional_value=notional_value,
            entry_price=entry_price,
            mark_price=mark_price,
            unrealized_pnl=unrealized_pnl,
            leverage=leverage,
            margin_used=margin_used,
            timestamp=time.time(),
        )

    def _sync_expected_positions(self, exchanges: Set[str]):
        """Refresh expected positions based on active positions."""
        self.position_tracker.expected_positions = {}
        self.position_tracker.expected_balances = {}

        for position_data in self.active_positions.values():
            trading_pair = position_data.get('trading_pair')
            edge = position_data.get('edge_decomposition')
            if not trading_pair:
                continue

            long_exchange = position_data.get('long_exchange')
            if long_exchange in exchanges:
                long_amount = position_data.get('long_amount_base')
                long_entry = position_data.get('entry_price_long')
                long_notional = position_data.get('long_notional')
                if long_amount is not None and long_entry is not None:
                    leverage_long = getattr(edge, 'leverage_long', Decimal("1")) if edge else Decimal("1")
                    if leverage_long <= 0:
                        leverage_long = Decimal("1")
                    if long_notional is None:
                        long_notional = abs(long_amount) * long_entry
                    long_mark = self._get_mid_price(self.exchanges[long_exchange], trading_pair)
                    snapshot = self._build_position_snapshot(
                        exchange=long_exchange,
                        trading_pair=trading_pair,
                        side='long',
                        size=Decimal(str(long_amount)),
                        entry_price=Decimal(str(long_entry)),
                        leverage=Decimal(str(leverage_long)),
                        unrealized_pnl=Decimal("0"),
                        mark_price=long_mark,
                    )
                    self.position_tracker.add_expected_position(snapshot)

            short_exchange = position_data.get('short_exchange')
            if short_exchange in exchanges:
                short_amount = position_data.get('short_amount_base')
                short_entry = position_data.get('entry_price_short')
                short_notional = position_data.get('short_notional')
                if short_amount is not None and short_entry is not None:
                    leverage_short = getattr(edge, 'leverage_short', Decimal("1")) if edge else Decimal("1")
                    if leverage_short <= 0:
                        leverage_short = Decimal("1")
                    if short_notional is None:
                        short_notional = abs(short_amount) * short_entry
                    short_mark = self._get_mid_price(self.exchanges[short_exchange], trading_pair)
                    snapshot = self._build_position_snapshot(
                        exchange=short_exchange,
                        trading_pair=trading_pair,
                        side='short',
                        size=Decimal(str(short_amount)),
                        entry_price=Decimal(str(short_entry)),
                        leverage=Decimal(str(leverage_short)),
                        unrealized_pnl=Decimal("0"),
                        mark_price=short_mark,
                    )
                    self.position_tracker.add_expected_position(snapshot)

    async def _collect_reconciliation_data(self) -> Optional[Tuple[
        Dict[str, PositionSnapshot],
        Dict[str, BalanceSnapshot],
        Optional[Dict[str, Dict]],
    ]]:
        """Collect actual positions/balances for reconciliation."""
        actual_positions: Dict[str, PositionSnapshot] = {}
        actual_balances: Dict[str, BalanceSnapshot] = {}
        actual_orders: Dict[str, Dict] = {}
        available_exchanges: Set[str] = set()

        for exchange_name, connector in self.exchanges.items():
            positions = self._get_connector_positions(connector)
            balances = self._get_connector_balances(connector)

            if positions is None and balances is None:
                continue

            if positions is not None:
                for position in positions:
                    try:
                        trading_pair = position.trading_pair
                        side = position.position_side.name.lower() if position.position_side else 'unknown'
                        amount = Decimal(str(position.amount))
                        entry_price = Decimal(str(position.entry_price))
                        leverage = Decimal(str(position.leverage)) if position.leverage else Decimal("1")
                        unrealized_pnl = Decimal(str(position.unrealized_pnl)) if position.unrealized_pnl is not None else Decimal("0")
                        mark_price = self._get_mid_price(connector, trading_pair)
                        snapshot = self._build_position_snapshot(
                            exchange=exchange_name,
                            trading_pair=trading_pair,
                            side=side,
                            size=amount,
                            entry_price=entry_price,
                            leverage=leverage if leverage > 0 else Decimal("1"),
                            unrealized_pnl=unrealized_pnl,
                            mark_price=mark_price,
                        )
                        key = f"{exchange_name}_{trading_pair}_{side}"
                        actual_positions[key] = snapshot
                        available_exchanges.add(exchange_name)
                    except Exception:
                        continue

            if balances is not None:
                for asset, total in balances.items():
                    try:
                        total_dec = Decimal(str(total))
                    except Exception:
                        continue
                    available = self._get_available_balance(connector, asset)
                    locked = max(total_dec - available, Decimal("0"))
                    key = f"{exchange_name}_{asset}"
                    actual_balances[key] = BalanceSnapshot(
                        exchange=exchange_name,
                        asset=asset,
                        total_balance=total_dec,
                        available_balance=available,
                        locked_balance=locked,
                        timestamp=time.time(),
                    )
                    available_exchanges.add(exchange_name)

            if hasattr(connector, 'in_flight_orders'):
                try:
                    for order_id, order in connector.in_flight_orders.items():
                        actual_orders[str(order_id)] = {
                            'exchange': exchange_name,
                            'order': order,
                        }
                except Exception:
                    pass

        if not available_exchanges:
            return None

        self._sync_expected_positions(available_exchanges)

        return actual_positions, actual_balances, actual_orders or None

    def _get_collateral_token(self, connector: ConnectorBase, trading_pair: str) -> Optional[str]:
        """Derive collateral token from connector or trading pair."""
        if hasattr(connector, 'get_buy_collateral_token'):
            try:
                return connector.get_buy_collateral_token(trading_pair)
            except Exception:
                pass
        if hasattr(connector, 'get_sell_collateral_token'):
            try:
                return connector.get_sell_collateral_token(trading_pair)
            except Exception:
                pass
        _, quote = self._split_trading_pair(connector, trading_pair)
        return quote

    def _get_strategy_positions_for_exchange(self, exchange_name: str) -> List[Dict]:
        """Build position views from strategy state when connector lacks positions."""
        positions = []
        for position_data in self.active_positions.values():
            trading_pair = position_data.get('trading_pair')
            edge = position_data.get('edge_decomposition')
            if not trading_pair:
                continue

            if position_data.get('long_exchange') == exchange_name:
                amount = position_data.get('long_amount_base')
                entry_price = position_data.get('entry_price_long')
                if amount is not None and entry_price is not None:
                    leverage = getattr(edge, 'leverage_long', Decimal("1")) if edge else Decimal("1")
                    positions.append({
                        'trading_pair': trading_pair,
                        'side': 'long',
                        'amount': Decimal(str(amount)),
                        'entry_price': Decimal(str(entry_price)),
                        'leverage': Decimal(str(leverage)) if leverage else Decimal("1"),
                        'unrealized_pnl': Decimal("0"),
                    })

            if position_data.get('short_exchange') == exchange_name:
                amount = position_data.get('short_amount_base')
                entry_price = position_data.get('entry_price_short')
                if amount is not None and entry_price is not None:
                    leverage = getattr(edge, 'leverage_short', Decimal("1")) if edge else Decimal("1")
                    positions.append({
                        'trading_pair': trading_pair,
                        'side': 'short',
                        'amount': Decimal(str(amount)),
                        'entry_price': Decimal(str(entry_price)),
                        'leverage': Decimal(str(leverage)) if leverage else Decimal("1"),
                        'unrealized_pnl': Decimal("0"),
                    })

        return positions

    async def _update_margin_monitoring(self):
        """Feed margin monitor with account and position snapshots."""
        self.margin_monitor.position_margins = {}
        self.margin_monitor.margin_snapshots = {}

        for exchange_name, connector in self.exchanges.items():
            positions = self._get_connector_positions(connector)
            using_strategy_positions = False
            if not positions:
                positions = self._get_strategy_positions_for_exchange(exchange_name)
                using_strategy_positions = True

            used_margin = Decimal("0")
            sample_trading_pair = None

            for position in positions:
                if using_strategy_positions:
                    trading_pair = position['trading_pair']
                    side = position['side']
                    amount = position['amount']
                    entry_price = position['entry_price']
                    leverage = position['leverage'] if position['leverage'] > 0 else Decimal("1")
                    unrealized_pnl = position['unrealized_pnl']
                else:
                    trading_pair = position.trading_pair
                    side = position.position_side.name.lower() if position.position_side else 'unknown'
                    amount = Decimal(str(position.amount))
                    entry_price = Decimal(str(position.entry_price))
                    leverage = Decimal(str(position.leverage)) if position.leverage else Decimal("1")
                    if leverage <= 0:
                        leverage = Decimal("1")
                    unrealized_pnl = Decimal(str(position.unrealized_pnl)) if position.unrealized_pnl is not None else Decimal("0")

                notional_value = abs(amount) * entry_price
                initial_margin = notional_value / leverage if leverage > 0 else notional_value
                maintenance_margin = initial_margin * Decimal("0.5")
                mark_price = self._get_mid_price(connector, trading_pair)

                position_id = f"{exchange_name}_{trading_pair}_{side}"
                self.margin_monitor.update_position_margin(PositionMarginInfo(
                    position_id=position_id,
                    exchange=exchange_name,
                    trading_pair=trading_pair,
                    side=side,
                    size=abs(amount),
                    notional_value=notional_value,
                    leverage=leverage,
                    initial_margin=initial_margin,
                    maintenance_margin=maintenance_margin,
                    unrealized_pnl=unrealized_pnl,
                    liquidation_price=None,
                    current_mark_price=mark_price,
                    adl_indicator=None,
                    timestamp=time.time(),
                ))

                used_margin += initial_margin
                if sample_trading_pair is None:
                    sample_trading_pair = trading_pair

            if sample_trading_pair is None:
                if self.trading_pairs:
                    sample_trading_pair = self.trading_pairs[0]
                else:
                    continue

            collateral_token = self._get_collateral_token(connector, sample_trading_pair)
            if collateral_token is None:
                continue

            total_equity = self._get_total_balance(connector, collateral_token)
            available_balance = self._get_available_balance(connector, collateral_token)
            locked_balance = max(total_equity - available_balance, Decimal("0"))

            if total_equity <= 0 and used_margin <= 0:
                continue

            if used_margin <= 0:
                margin_ratio = Decimal("999")
            else:
                margin_ratio = total_equity / used_margin

            free_margin = max(total_equity - used_margin, Decimal("0"))
            maintenance_margin = used_margin * Decimal("0.5")

            self.margin_monitor.update_margin_info(MarginInfo(
                exchange=exchange_name,
                account_id=None,
                total_equity=total_equity,
                used_margin=used_margin,
                free_margin=free_margin,
                margin_ratio=margin_ratio,
                maintenance_margin=maintenance_margin,
                initial_margin_req=used_margin,
                liquidation_price=None,
                timestamp=time.time(),
            ))

    async def _calculate_position_size(self,
                                     trading_pair: str,
                                     long_exchange: str,
                                     short_exchange: str) -> Decimal:
        """
        Calculate safe position size based on risk limits and configuration.

        Uses config.order_amount as the base size, then applies risk multipliers.
        """
        # Base position size from configuration (in notional USD value)
        base_size = self.config.order_amount

        # Note: config.order_amount is per position, we interpret it as notional USD value
        # For perpetual contracts, this is straightforward
        # For spot markets with leverage, this would be the base currency amount

        # Validate base_size is reasonable
        if base_size <= 0:
            self.logger().warning(
                f"Invalid order_amount in config: {base_size}, using default $1000"
            )
            base_size = Decimal("1000")

        # Check risk limits
        can_open_long, _, risk_level_long = self.risk_manager.check_position_limits(
            exchange=long_exchange,
            subaccount=None,
            trading_pair=trading_pair,
            proposed_notional=base_size,
            proposed_leverage=Decimal("1")
        )

        can_open_short, _, risk_level_short = self.risk_manager.check_position_limits(
            exchange=short_exchange,
            subaccount=None,
            trading_pair=trading_pair,
            proposed_notional=base_size,
            proposed_leverage=Decimal("1")
        )

        if not can_open_long or not can_open_short:
            return Decimal("0")

        # Adjust size based on risk level
        risk_multipliers = {
            'low': Decimal("1.0"),
            'medium': Decimal("0.7"),
            'high': Decimal("0.3"),
            'critical': Decimal("0")
        }

        multiplier = min(
            risk_multipliers.get(risk_level_long.value, Decimal("0")),
            risk_multipliers.get(risk_level_short.value, Decimal("0"))
        )

        return base_size * multiplier

    async def _evaluate_and_execute_opportunity(self, opportunity: Dict):
        """Evaluate timing and execute arbitrage opportunity."""
        trading_pair = opportunity['trading_pair']
        long_exchange = opportunity['long_exchange']
        short_exchange = opportunity['short_exchange']
        edge = opportunity['edge_decomposition']

        self.logger().info(f"Evaluating opportunity: {trading_pair} on {long_exchange}/{short_exchange}, edge={edge.total_edge:.6f}")

        # Check funding settlement timing
        settlement_status, minutes_to_settlement = self.funding_scheduler.get_settlement_status(
            [long_exchange, short_exchange]
        )

        should_open, timing_reason = self.funding_scheduler.should_open_position(
            [long_exchange, short_exchange],
            minimum_time_horizon_minutes=self.config.min_position_hold_time_minutes
        )

        if not should_open:
            self.opportunities_skipped_by_reason[f"timing_{timing_reason}"] = \
                self.opportunities_skipped_by_reason.get(f"timing_{timing_reason}", 0) + 1
            return

        # CRITICAL FIX: Get real-time liquidity from order book BEFORE checking
        self.logger().info("Fetching order book liquidity data...")

        long_liquidity = await self._get_order_book_liquidity(
            self.exchanges[long_exchange], trading_pair
        )
        short_liquidity = await self._get_order_book_liquidity(
            self.exchanges[short_exchange], trading_pair
        )

        # Update risk manager cache with fresh data
        if long_liquidity:
            self.risk_manager.update_liquidity_metrics(long_liquidity)
            self.logger().debug(
                f"Long liquidity ({long_exchange}): "
                f"bid_1%={long_liquidity.bid_depth_1pct:.2f}, "
                f"ask_1%={long_liquidity.ask_depth_1pct:.2f}"
            )
        else:
            self.logger().warning(f"Failed to get order book liquidity for {long_exchange}/{trading_pair}")

        if short_liquidity:
            self.risk_manager.update_liquidity_metrics(short_liquidity)
            self.logger().debug(
                f"Short liquidity ({short_exchange}): "
                f"bid_1%={short_liquidity.bid_depth_1pct:.2f}, "
                f"ask_1%={short_liquidity.ask_depth_1pct:.2f}"
            )
        else:
            self.logger().warning(f"Failed to get order book liquidity for {short_exchange}/{trading_pair}")

        # Check liquidity (now with real data from order book!)
        liquidity_ok_long, liquidity_reason_long, impact_long = self.risk_manager.check_liquidity_risk(
            long_exchange, trading_pair, edge.notional_amount
        )
        liquidity_ok_short, liquidity_reason_short, impact_short = self.risk_manager.check_liquidity_risk(
            short_exchange, trading_pair, edge.notional_amount
        )

        self.logger().info(
            f"Liquidity check: long={liquidity_ok_long} ({liquidity_reason_long}), "
            f"short={liquidity_ok_short} ({liquidity_reason_short})"
        )

        if not liquidity_ok_long or not liquidity_ok_short:
            self.opportunities_skipped_by_reason["liquidity"] = \
                self.opportunities_skipped_by_reason.get("liquidity", 0) + 1
            self.logger().info("Skipping due to insufficient liquidity")
            return

        # Execute the arbitrage
        await self._execute_arbitrage(opportunity)

    async def _execute_arbitrage(self, opportunity: Dict):
        """
        Execute the arbitrage trade with proper rollback on failures.
        Uses parallel execution for both legs and verifies hedge is properly established.
        """
        trading_pair = opportunity['trading_pair']
        long_exchange = opportunity['long_exchange']
        short_exchange = opportunity['short_exchange']
        edge = opportunity['edge_decomposition']

        self.logger().info(f"Executing arbitrage: {trading_pair} long on {long_exchange}, short on {short_exchange}")
        self.logger().info(f"Edge decomposition: {edge.to_display_dict()}")

        long_connector = self.exchanges[long_exchange]
        short_connector = self.exchanges[short_exchange]

        long_price = self._get_mid_price(long_connector, trading_pair)
        short_price = self._get_mid_price(short_connector, trading_pair)
        if long_price is None or short_price is None:
            raise Exception("Mid price unavailable for position sizing")

        long_amount_base = edge.notional_amount / long_price
        short_amount_base = edge.notional_amount / short_price

        if long_amount_base <= 0 or short_amount_base <= 0:
            raise Exception("Invalid base amount calculated from mid prices")

        long_order_id = None
        short_order_id = None
        long_filled_amount = Decimal("0")
        short_filled_amount = Decimal("0")

        try:
            # Phase 1: Place both orders in parallel for minimal execution lag
            self.logger().info("Phase 1: Placing orders in parallel...")

            async def place_long():
                return await self._place_order(
                    connector=long_connector,
                    trading_pair=trading_pair,
                    is_buy=True,
                    amount=long_amount_base,
                    position_action=PositionAction.OPEN
                )

            async def place_short():
                return await self._place_order(
                    connector=short_connector,
                    trading_pair=trading_pair,
                    is_buy=False,
                    amount=short_amount_base,
                    position_action=PositionAction.OPEN
                )

            # Execute both orders in parallel with exception handling
            # CRITICAL: Use return_exceptions=True to handle failures safely
            results = await asyncio.gather(
                place_long(),
                place_short(),
                return_exceptions=True
            )

            long_result, short_result = results

            # Check if either order failed
            if isinstance(long_result, Exception):
                self.logger().error(f"Long order placement failed: {long_result}")
                # If short order succeeded, we need to cancel/close it
                if not isinstance(short_result, Exception):
                    short_order_id = short_result
                    self.logger().error("Short order succeeded but long failed, emergency closing short")
                    try:
                        await self._emergency_close(
                            short_connector, trading_pair, is_long=False,
                            amount=short_amount_base, reason="Long order placement failed"
                        )
                    except Exception as e:
                        self.logger().error(f"Failed to emergency close short after long failure: {e}")
                raise Exception(f"Long order placement failed: {long_result}")

            if isinstance(short_result, Exception):
                self.logger().error(f"Short order placement failed: {short_result}")
                # Long succeeded but short failed - close the long position
                long_order_id = long_result
                self.logger().error("Long order succeeded but short failed, emergency closing long")
                try:
                    await self._emergency_close(
                        long_connector, trading_pair, is_long=True,
                        amount=long_amount_base, reason="Short order placement failed"
                    )
                except Exception as e:
                    self.logger().error(f"Failed to emergency close long after short failure: {e}")
                raise Exception(f"Short order placement failed: {short_result}")

            # Both succeeded
            long_order_id = long_result
            short_order_id = short_result

            self.logger().info(f"Orders placed: long={long_order_id}, short={short_order_id}")

            # Phase 2: Verify both orders filled
            self.logger().info("Phase 2: Verifying order fills...")

            async def verify_long():
                return await self._verify_order_filled(
                    long_connector, long_order_id, timeout_seconds=30
                )

            async def verify_short():
                return await self._verify_order_filled(
                    short_connector, short_order_id, timeout_seconds=30
                )

            # Verify both fills in parallel with exception handling
            # CRITICAL: Use return_exceptions=True to handle failures safely
            verify_results = await asyncio.gather(
                verify_long(),
                verify_short(),
                return_exceptions=True
            )

            long_verify_result, short_verify_result = verify_results

            # Check if verification failed
            if isinstance(long_verify_result, Exception):
                self.logger().error(f"Long order verification failed: {long_verify_result}")
                # Try to close short if it exists
                if not isinstance(short_verify_result, Exception):
                    try:
                        short_filled, short_amount = short_verify_result
                        if short_filled:
                            await self._emergency_close(
                                short_connector, trading_pair, is_long=False,
                                amount=short_amount, reason="Long verification failed"
                            )
                    except Exception as e:
                        self.logger().error(f"Failed cleanup after long verification failure: {e}")
                raise Exception(f"Long order verification failed: {long_verify_result}")

            if isinstance(short_verify_result, Exception):
                self.logger().error(f"Short order verification failed: {short_verify_result}")
                # Long verification succeeded - close it
                try:
                    long_filled, long_amount = long_verify_result
                    if long_filled:
                        await self._emergency_close(
                            long_connector, trading_pair, is_long=True,
                            amount=long_amount, reason="Short verification failed"
                        )
                except Exception as e:
                    self.logger().error(f"Failed cleanup after short verification failure: {e}")
                raise Exception(f"Short order verification failed: {short_verify_result}")

            # Both verifications succeeded
            (long_filled, long_amount) = long_verify_result
            (short_filled, short_amount) = short_verify_result

            long_filled_amount = long_amount
            short_filled_amount = short_amount

            # Check if both orders filled successfully
            if not long_filled:
                self.logger().error("Long order not filled, rolling back...")
                if short_filled:
                    # Close the short position that was filled
                    await self._emergency_close(
                        short_connector, trading_pair, is_long=False,
                        amount=short_amount, reason="Long order failed to fill"
                    )
                raise Exception(f"Long order {long_order_id} not filled")

            if not short_filled:
                self.logger().error("Short order not filled, rolling back...")
                # Close the long position that was filled
                await self._emergency_close(
                    long_connector, trading_pair, is_long=True,
                    amount=long_amount, reason="Short order failed to fill"
                )
                raise Exception(f"Short order {short_order_id} not filled")

            self.logger().info(f"Both orders filled: long={long_amount}, short={short_amount}")

            # Phase 3: Verify hedge gap is acceptable
            self.logger().info("Phase 3: Checking hedge gap...")

            hedge_ok, gap_pct = await self._check_hedge_gap(
                long_connector, short_connector, trading_pair,
                expected_amount=max(long_filled_amount, short_filled_amount),
                max_gap_pct=self.config.max_hedge_gap_percentage
            )

            if not hedge_ok:
                self.logger().error(f"Hedge gap too large ({gap_pct:.2%}), closing both positions...")
                # Close both positions with exception handling
                close_results = await asyncio.gather(
                    self._emergency_close(
                        long_connector, trading_pair, is_long=True,
                        amount=long_amount, reason=f"Hedge gap {gap_pct:.2%} too large"
                    ),
                    self._emergency_close(
                        short_connector, trading_pair, is_long=False,
                        amount=short_amount, reason=f"Hedge gap {gap_pct:.2%} too large"
                    ),
                    return_exceptions=True
                )

                # Log any close failures
                for i, result in enumerate(close_results):
                    if isinstance(result, Exception):
                        side = "long" if i == 0 else "short"
                        self.logger().error(f"Failed to emergency close {side} position: {result}")

                raise Exception(f"Hedge gap {gap_pct:.2%} exceeds maximum 5%")

            self.logger().info(f"Hedge gap acceptable: {gap_pct:.2%}")

            # Phase 4: Track the position
            position_id = f"arb_{trading_pair}_{int(time.time())}"
            long_notional = long_filled_amount * long_price
            short_notional = short_filled_amount * short_price

            self.active_positions[position_id] = {
                'trading_pair': trading_pair,
                'long_exchange': long_exchange,
                'short_exchange': short_exchange,
                'long_order_id': long_order_id,
                'short_order_id': short_order_id,
                'long_amount_base': long_filled_amount,
                'short_amount_base': short_filled_amount,
                'long_notional': long_notional,
                'short_notional': short_notional,
                'notional_amount': edge.notional_amount,
                'expected_edge': edge.total_edge,
                'entry_time': time.time(),
                'entry_price_long': long_price,
                'entry_price_short': short_price,
                'edge_decomposition': edge
            }

            # Update risk trackers
            long_position = PositionInfo(
                exchange=long_exchange,
                subaccount=None,
                trading_pair=trading_pair,
                notional_amount=long_notional,
                leverage=edge.leverage_long,
                side='long',
                timestamp=time.time(),
                order_ids=[long_order_id]
            )

            short_position = PositionInfo(
                exchange=short_exchange,
                subaccount=None,
                trading_pair=trading_pair,
                notional_amount=short_notional,
                leverage=edge.leverage_short,
                side='short',
                timestamp=time.time(),
                order_ids=[short_order_id]
            )

            self.risk_manager.add_position(long_position)
            self.risk_manager.add_position(short_position)

            self.total_trades_executed += 1
            self.profitable_opportunities_taken += 1

            self.logger().info(f" Arbitrage position {position_id} opened successfully")

        except Exception as e:
            self.logger().error(f" Failed to execute arbitrage: {e}")
            # Position tracking not added since we failed or rolled back
            raise

    async def _place_order(self,
                         connector: ConnectorBase,
                         trading_pair: str,
                         is_buy: bool,
                         amount: Decimal,
                         price: Optional[Decimal] = None,
                         position_action: PositionAction = PositionAction.NIL) -> str:
        """
        Place order on exchange with proper error handling.

        Args:
            connector: Exchange connector
            trading_pair: Trading pair symbol
            is_buy: True for buy, False for sell
            amount: Order amount in base currency
            price: Optional limit price (None for market orders)
            position_action: OPEN/CLOSE intent for derivatives

        Returns:
            Order ID from exchange

        Raises:
            Exception: If order placement fails
        """
        order_type = OrderType.MARKET if price is None else OrderType.LIMIT

        try:
            # NOTE: connector.buy() and connector.sell() are SYNCHRONOUS methods in Hummingbot
            # They create the order locally and return the client_order_id immediately
            # The actual order placement happens asynchronously via the connector's event loop
            if is_buy:
                order_id = connector.buy(
                    trading_pair=trading_pair,
                    amount=amount,
                    order_type=order_type,
                    price=price,
                    position_action=position_action
                )
            else:
                order_id = connector.sell(
                    trading_pair=trading_pair,
                    amount=amount,
                    order_type=order_type,
                    price=price,
                    position_action=position_action
                )

            self.logger().info(
                f"Placed {'BUY' if is_buy else 'SELL'} order {order_id} on {connector.name}: "
                f"{amount} {trading_pair} @ {'MARKET' if price is None else price}"
            )

            # Wait a short time to allow the order to be submitted to exchange
            await asyncio.sleep(0.5)

            return order_id

        except Exception as e:
            self.logger().error(
                f"Failed to place {'BUY' if is_buy else 'SELL'} order on {connector.name}: {e}"
            )
            raise

    async def _verify_order_filled(self,
                                  connector: ConnectorBase,
                                  order_id: str,
                                  timeout_seconds: int = 30,
                                  min_fill_ratio: Decimal = Decimal("0.90")) -> Tuple[bool, Decimal]:
        """
        Verify that an order was filled.

        Args:
            connector: Exchange connector
            order_id: Order ID to verify
            timeout_seconds: Maximum time to wait for fill
            min_fill_ratio: Minimum fill ratio to consider successful (0.90 = 90%)

        Returns:
            Tuple of (is_filled, filled_amount)
        """
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                # NOTE: get_order() is a SYNCHRONOUS method that returns cached state
                # For in-flight orders, use in_flight_orders tracker
                order = None

                # Try to get from in_flight_orders first (most reliable)
                if hasattr(connector, 'in_flight_orders') and order_id in connector.in_flight_orders:
                    order = connector.in_flight_orders[order_id]
                # Fallback to get_order if available
                elif hasattr(connector, 'get_order'):
                    order = connector.get_order(order_id)

                if order is None:
                    await asyncio.sleep(0.5)
                    continue

                # Check if order is filled
                # Different connectors may have different attributes
                is_done = False
                if hasattr(order, 'is_done'):
                    is_done = order.is_done
                elif hasattr(order, 'is_filled'):
                    is_done = order.is_filled
                elif hasattr(order, 'state') and hasattr(order, 'OrderState'):
                    is_done = order.state in ['FILLED', 'COMPLETED']

                if is_done:
                    # Get filled amount
                    filled_amount = Decimal("0")
                    if hasattr(order, 'executed_amount_base'):
                        filled_amount = Decimal(str(order.executed_amount_base))
                    elif hasattr(order, 'filled_amount'):
                        filled_amount = Decimal(str(order.filled_amount))
                    elif hasattr(order, 'amount'):
                        filled_amount = Decimal(str(order.amount))

                    order_amount = Decimal(str(order.amount)) if hasattr(order, 'amount') else filled_amount

                    if order_amount > 0:
                        fill_ratio = filled_amount / order_amount
                    else:
                        fill_ratio = Decimal("0")

                    # Accept fills >= 90% (more lenient for real market conditions)
                    if fill_ratio >= min_fill_ratio:
                        self.logger().info(
                            f"Order {order_id} filled: {filled_amount}/{order_amount} ({fill_ratio:.1%})"
                        )
                        return True, filled_amount
                    elif fill_ratio >= Decimal("0.5"):
                        # Partial fill >= 50% - log warning but accept it
                        self.logger().warning(
                            f"Order {order_id} partially filled: {fill_ratio:.1%}, accepting it"
                        )
                        return True, filled_amount
                    else:
                        # Too low fill ratio
                        self.logger().warning(
                            f"Order {order_id} only {fill_ratio:.1%} filled, rejecting"
                        )
                        return False, filled_amount

                await asyncio.sleep(0.5)

            except Exception as e:
                self.logger().warning(f"Error checking order {order_id}: {e}")
                await asyncio.sleep(1)

        self.logger().error(f"Order {order_id} verification timeout after {timeout_seconds}s")

        # On timeout, try one last time to get any partial fill
        try:
            if hasattr(connector, 'in_flight_orders') and order_id in connector.in_flight_orders:
                order = connector.in_flight_orders[order_id]
                if hasattr(order, 'executed_amount_base'):
                    partial_fill = Decimal(str(order.executed_amount_base))
                    if partial_fill > 0:
                        self.logger().warning(f"Order {order_id} timeout but has partial fill: {partial_fill}")
                        return False, partial_fill
        except Exception:
            pass

        return False, Decimal("0")

    async def _emergency_close(self,
                              connector: ConnectorBase,
                              trading_pair: str,
                              is_long: bool,
                              amount: Decimal,
                              reason: str = "Emergency close"):
        """
        Emergency close a position immediately.

        Args:
            connector: Exchange connector
            trading_pair: Trading pair symbol
            is_long: True if closing long position (will sell), False if closing short (will buy)
            amount: Amount to close
            reason: Reason for emergency close
        """
        try:
            self.logger().warning(f"EMERGENCY CLOSE: {reason} - {'SELL' if is_long else 'BUY'} {amount} {trading_pair}")

            # Place market order to close position
            close_order_id = await self._place_order(
                connector=connector,
                trading_pair=trading_pair,
                is_buy=not is_long,  # Sell to close long, buy to close short
                amount=amount,
                price=None,  # Market order for immediate execution
                position_action=PositionAction.CLOSE
            )

            # Wait for fill (shorter timeout for emergency)
            filled, filled_amount = await self._verify_order_filled(
                connector, close_order_id, timeout_seconds=15
            )

            if not filled:
                self.logger().critical(
                    f"Emergency close order {close_order_id} not filled! Manual intervention required!"
                )
            else:
                self.logger().info(f"Emergency close successful: {filled_amount} closed")

        except Exception as e:
            self.logger().critical(f"Emergency close FAILED: {e} - MANUAL INTERVENTION REQUIRED!")

    async def _check_hedge_gap(self,
                              long_connector: ConnectorBase,
                              short_connector: ConnectorBase,
                              trading_pair: str,
                              expected_amount: Decimal,
                              max_gap_pct: Decimal = Decimal("0.05")) -> Tuple[bool, Decimal]:
        """
        Check if hedge gap is within acceptable limits after position opening.

        Args:
            long_connector: Connector for long position
            short_connector: Connector for short position
            trading_pair: Trading pair
            expected_amount: Expected position size
            max_gap_pct: Maximum acceptable gap (0.05 = 5%)

        Returns:
            Tuple of (is_acceptable, gap_percentage)
        """
        try:
            # Get actual position sizes from exchanges
            long_position = await self._get_position_size(long_connector, trading_pair, 'long')
            short_position = await self._get_position_size(short_connector, trading_pair, 'short')

            # Calculate gap
            gap_amount = abs(long_position - short_position)
            gap_percentage = gap_amount / expected_amount if expected_amount > 0 else Decimal("1")

            is_acceptable = gap_percentage <= max_gap_pct

            if not is_acceptable:
                self.logger().warning(
                    f"Hedge gap too large: {gap_percentage:.2%} "
                    f"(long={long_position}, short={short_position}, expected={expected_amount})"
                )

            return is_acceptable, gap_percentage

        except Exception as e:
            self.logger().error(f"Failed to check hedge gap: {e}")
            return False, Decimal("1")  # Assume worst case

    async def _get_position_size(self,
                                connector: ConnectorBase,
                                trading_pair: str,
                                side: str) -> Decimal:
        """
        Get current position size from exchange.

        Args:
            connector: Exchange connector
            trading_pair: Trading pair
            side: 'long' or 'short'

        Returns:
            Position size (absolute value)
        """
        try:
            if hasattr(connector, 'get_position'):
                position = connector.get_position(trading_pair)
                if position:
                    return abs(position.amount)
            return Decimal("0")
        except Exception as e:
            self.logger().warning(f"Failed to get position size: {e}")
            return Decimal("0")

    async def _monitor_existing_positions(self):
        """Monitor existing positions for closing opportunities."""
        positions_to_close = []

        for position_id, position_data in self.active_positions.items():
            # Check if position should be closed due to timing
            exchanges = [position_data['long_exchange'], position_data['short_exchange']]
            position_age_minutes = (time.time() - position_data['entry_time']) / 60

            should_close, close_reason = self.funding_scheduler.should_close_position(
                exchanges,
                position_age_minutes,
                self.config.min_position_hold_time_minutes
            )

            if should_close:
                positions_to_close.append((position_id, close_reason))

        # Close positions that need closing
        for position_id, reason in positions_to_close:
            await self._close_position(position_id, reason)

    async def _close_position(self, position_id: str, reason: str):
        """
        Close an arbitrage position by closing both legs.
        Closes both positions in parallel for minimal slippage.
        """
        if position_id not in self.active_positions:
            self.logger().warning(f"Position {position_id} not found in active positions")
            return

        position_data = self.active_positions[position_id]
        self.logger().info(f"Closing position {position_id}: {reason}")

        trading_pair = position_data['trading_pair']
        long_exchange = position_data['long_exchange']
        short_exchange = position_data['short_exchange']
        long_amount = position_data.get('long_amount_base', position_data.get('long_amount'))
        short_amount = position_data.get('short_amount_base', position_data.get('short_amount'))

        if long_amount is None or short_amount is None:
            self.logger().error(f"Missing base amounts for {position_id}, cannot close position safely")
            return

        long_connector = self.exchanges[long_exchange]
        short_connector = self.exchanges[short_exchange]

        try:
            # Close both positions in parallel for minimal slippage
            self.logger().info(f"Closing long {long_amount} on {long_exchange} and short {short_amount} on {short_exchange}")

            async def close_long():
                # Sell to close long position
                order_id = await self._place_order(
                    connector=long_connector,
                    trading_pair=trading_pair,
                    is_buy=False,  # SELL to close long
                    amount=long_amount,
                    position_action=PositionAction.CLOSE
                )
                filled, filled_amount = await self._verify_order_filled(
                    long_connector, order_id, timeout_seconds=30
                )
                return filled, filled_amount

            async def close_short():
                # Buy to close short position
                order_id = await self._place_order(
                    connector=short_connector,
                    trading_pair=trading_pair,
                    is_buy=True,  # BUY to close short
                    amount=short_amount,
                    position_action=PositionAction.CLOSE
                )
                filled, filled_amount = await self._verify_order_filled(
                    short_connector, order_id, timeout_seconds=30
                )
                return filled, filled_amount

            # Execute both closes in parallel with exception handling
            # CRITICAL: Use return_exceptions=True to handle failures safely
            close_results = await asyncio.gather(
                close_long(),
                close_short(),
                return_exceptions=True
            )

            long_close_result, short_close_result = close_results

            # Handle close results
            long_closed = False
            long_closed_amount = Decimal("0")
            short_closed = False
            short_closed_amount = Decimal("0")

            if isinstance(long_close_result, Exception):
                self.logger().error(f"Failed to close long position: {long_close_result}")
            else:
                long_closed, long_closed_amount = long_close_result

            if isinstance(short_close_result, Exception):
                self.logger().error(f"Failed to close short position: {short_close_result}")
            else:
                short_closed, short_closed_amount = short_close_result

            # Check results
            if not long_closed or not short_closed:
                self.logger().error(
                    f"Failed to close position {position_id} completely: "
                    f"long_closed={long_closed}, short_closed={short_closed}"
                )
                position_data["close_attempts"] = position_data.get("close_attempts", 0) + 1
                position_data["last_close_reason"] = reason
                position_data["last_close_timestamp"] = time.time()
                self.logger().critical(
                    f"MANUAL INTERVENTION REQUIRED: {position_id} close failed; "
                    "position remains tracked for retry."
                )
                return

            # Calculate actual PnL
            # In real implementation, this would fetch actual funding payments received
            # For now, use expected edge as estimate
            estimated_pnl = position_data['expected_edge']
            position_duration_hours = (time.time() - position_data['entry_time']) / 3600

            self.total_funding_collected += estimated_pnl

            self.logger().info(
                f" Position {position_id} closed: "
                f"long={long_closed_amount}, short={short_closed_amount}, "
                f"duration={position_duration_hours:.1f}h, estimated_pnl={estimated_pnl:.4f}"
            )

            # Remove from tracking
            del self.active_positions[position_id]

            # Remove from risk manager
            self.risk_manager.remove_position_by_exchange_pair(long_exchange, trading_pair)
            self.risk_manager.remove_position_by_exchange_pair(short_exchange, trading_pair)

        except Exception as e:
            self.logger().error(f" Failed to close position {position_id}: {e}")
            position_data["close_attempts"] = position_data.get("close_attempts", 0) + 1
            position_data["last_close_error"] = str(e)
            position_data["last_close_timestamp"] = time.time()
            raise

    def start(self):
        """Start the strategy."""
        super().start()

        # Start monitoring components with task tracking
        # CRITICAL: Store task references to handle exceptions properly
        reconciliation_task = asyncio.create_task(self.reconciliation_scheduler.start())
        margin_task = asyncio.create_task(self.margin_monitor.run_monitoring_loop())

        # Add tasks to tracking set
        self._background_tasks.add(reconciliation_task)
        self._background_tasks.add(margin_task)

        # Add done callbacks to handle completion/exceptions
        reconciliation_task.add_done_callback(self._handle_background_task_done)
        margin_task.add_done_callback(self._handle_background_task_done)

        self.logger().info("Funding arbitrage strategy started")

    def stop(self):
        """Stop the strategy."""
        # Stop monitoring
        self.margin_monitor.stop_monitoring()

        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Stop reconciliation
        asyncio.create_task(self.reconciliation_scheduler.stop())

        # Close all positions
        for position_id in list(self.active_positions.keys()):
            asyncio.create_task(self._close_position(position_id, "Strategy stopping"))

        super().stop()
        self.logger().info("Funding arbitrage strategy stopped")

    def _handle_background_task_done(self, task: asyncio.Task):
        """
        Handle background task completion/failure.
        CRITICAL: Log exceptions to prevent silent failures.
        """
        # Remove from tracking set
        self._background_tasks.discard(task)

        try:
            # Check if task raised an exception
            exception = task.exception()
            if exception:
                self.logger().critical(
                    f"Background task failed with exception: {exception}",
                    exc_info=exception
                )
                # Optionally trigger emergency stop
                if self.config.emergency_stop_on_critical_issues:
                    self.emergency_stop_active = True
        except asyncio.CancelledError:
            # Task was cancelled, this is normal during shutdown
            self.logger().info("Background task was cancelled")
        except Exception as e:
            self.logger().error(f"Error checking background task result: {e}")

    def get_strategy_status(self) -> Dict:
        """Get comprehensive strategy status."""
        # Update real-time metrics
        self.metrics.set_gauge("positions_active", Decimal(len(self.active_positions)))
        self.metrics.set_gauge("positions_total_notional",
                              sum(Decimal(str(pos.get('notional_amount', 0)))
                                  for pos in self.active_positions.values()))

        return {
            'active_positions': len(self.active_positions),
            'total_trades': self.total_trades_executed,
            'profitable_opportunities': self.profitable_opportunities_taken,
            'total_funding_collected': float(self.total_funding_collected),
            'emergency_stop_active': self.emergency_stop_active,
            'opportunities_skipped': dict(self.opportunities_skipped_by_reason),
            'risk_summary': self.risk_manager.get_risk_summary(),
            'edge_tracker': {
                'profitability_rate': self.edge_tracker.get_profitability_rate(),
                'average_components': {
                    k: float(v) for k, v in self.edge_tracker.get_average_edge_components().items()
                }
            },
            'margin_monitoring': self.margin_monitor.get_monitoring_summary(),
            'reconciliation': self.reconciliation_engine.get_reconciliation_metrics(),
            'metrics': self.metrics.get_summary(window_seconds=3600),
            'metrics_dashboard': self.metrics.get_dashboard_summary(),
        }
