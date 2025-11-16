"""
Market-specific funding arbitrage strategy with comprehensive risk management.
Integrates all components: edge calculation, scheduling, risk management, reconciliation, and margin monitoring.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import time

from hummingbot.strategy.strategy_py_base import StrategyPyBase
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PositionAction, TradeType
from hummingbot.core.data_type.funding_info import FundingInfo
from hummingbot.core.event.events import BuyOrderCompletedEvent, SellOrderCompletedEvent
from hummingbot.logger import HummingbotLogger

from .edge_decomposition import EdgeCalculator, EdgeTracker, EdgeDecomposition
from .funding_scheduler import FundingScheduler, SettlementStatus
from .risk_management import RiskManager, PositionInfo, LiquidityMetrics
from .reconciliation import ReconciliationEngine, PositionTracker, ReconciliationScheduler
from .margin_monitoring import MarginMonitor, MarginInfo, PositionMarginInfo, MarginAction

logger = logging.getLogger(__name__)


@dataclass
class FundingArbitrageConfig:
    """Configuration for funding arbitrage strategy."""
    # Entry criteria
    min_edge_required: Decimal = Decimal("0.0005")  # 0.05%
    min_funding_rate_diff: Decimal = Decimal("0.0003")  # 0.03%
    min_position_hold_time_minutes: int = 10
    
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
            config.reconciliation_interval_seconds
        )
        
        # Margin monitoring
        self.margin_monitor = MarginMonitor(
            max_allowed_leverage=config.max_leverage,
            auto_reduce_enabled=config.auto_leverage_reduction
        )
        
        # State tracking
        self.active_positions: Dict[str, Dict] = {}  # position_id -> position_data
        self.funding_rates: Dict[str, Dict[str, FundingInfo]] = {}  # exchange -> pair -> FundingInfo
        self.last_funding_check = 0
        self.emergency_stop_active = False
        
        # Performance tracking
        self.total_funding_collected = Decimal("0")
        self.total_trades_executed = 0
        self.profitable_opportunities_taken = 0
        self.opportunities_skipped_by_reason: Dict[str, int] = {}
        
        self._setup_callbacks()
        
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
        """Handle leverage reduction for a position."""
        if position_id in self.active_positions:
            position_data = self.active_positions[position_id]
            self.logger().info(f"Reducing leverage for {position_id} to {new_leverage}")
            
            # Implement leverage reduction logic here
            # This would involve adjusting position size or adding margin
            
    async def _close_all_positions_on_exchange(self, exchange_name: str):
        """Close all active positions on a specific exchange."""
        positions_to_close = [
            pos_id for pos_id, pos_data in self.active_positions.items()
            if pos_data.get('exchange') == exchange_name
        ]
        
        for position_id in positions_to_close:
            await self._close_position(position_id, "Emergency exit")
    
    async def on_tick(self):
        """Main strategy tick - called periodically."""
        try:
            current_time = time.time()
            
            # Update funding rates
            if current_time - self.last_funding_check >= self.config.funding_check_interval_seconds:
                await self._update_funding_rates()
                self.last_funding_check = current_time
            
            # Check for arbitrage opportunities
            if not self.emergency_stop_active:
                await self._check_arbitrage_opportunities()
            
            # Monitor existing positions
            await self._monitor_existing_positions()
            
        except Exception as e:
            self.logger().error(f"Error in strategy tick: {e}")
    
    async def _update_funding_rates(self):
        """Update funding rates from all exchanges."""
        for exchange_name, connector in self.exchanges.items():
            try:
                for trading_pair in self.trading_pairs:
                    if hasattr(connector, 'get_funding_info'):
                        funding_info = await connector.get_funding_info(trading_pair)
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
                    if rate_diff < self.config.min_funding_rate_diff:
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
        
        # Get fee configuration (simplified - would come from exchange configs)
        fees_config = {
            exchange: {'maker': Decimal("0.0002"), 'taker': Decimal("0.0004")}
            for exchange in [long_exchange, short_exchange]
        }
        
        # Get borrow rates (simplified)
        borrow_rates = {'BTC': Decimal("0.0001"), 'USDT': Decimal("0.00005")}
        
        # Get slippage estimates (simplified)
        slippage_estimates = {
            exchange: Decimal("0.0005") for exchange in [long_exchange, short_exchange]
        }
        
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
            slippage_estimates=slippage_estimates
        )
        
        # Track the calculation
        self.edge_tracker.add_edge_calculation(edge)
        
        return edge
    
    async def _calculate_position_size(self, 
                                     trading_pair: str,
                                     long_exchange: str,
                                     short_exchange: str) -> Decimal:
        """Calculate safe position size based on risk limits."""
        # Base position size (could be configurable)
        base_size = Decimal("1000")  # $1000 USD equivalent
        
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
        
        # Check liquidity
        liquidity_ok_long, liquidity_reason_long, _ = self.risk_manager.check_liquidity_risk(
            long_exchange, trading_pair, edge.notional_amount
        )
        liquidity_ok_short, liquidity_reason_short, _ = self.risk_manager.check_liquidity_risk(
            short_exchange, trading_pair, edge.notional_amount
        )
        
        if not liquidity_ok_long or not liquidity_ok_short:
            self.opportunities_skipped_by_reason["liquidity"] = \
                self.opportunities_skipped_by_reason.get("liquidity", 0) + 1
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
                    amount=edge.notional_amount
                )

            async def place_short():
                return await self._place_order(
                    connector=short_connector,
                    trading_pair=trading_pair,
                    is_buy=False,
                    amount=edge.notional_amount
                )

            # Execute both orders in parallel
            long_order_id, short_order_id = await asyncio.gather(
                place_long(),
                place_short()
            )

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

            # Verify both fills in parallel
            (long_filled, long_amount), (short_filled, short_amount) = await asyncio.gather(
                verify_long(),
                verify_short()
            )

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
                expected_amount=edge.notional_amount,
                max_gap_pct=Decimal("0.05")
            )

            if not hedge_ok:
                self.logger().error(f"Hedge gap too large ({gap_pct:.2%}), closing both positions...")
                # Close both positions
                await asyncio.gather(
                    self._emergency_close(
                        long_connector, trading_pair, is_long=True,
                        amount=long_amount, reason=f"Hedge gap {gap_pct:.2%} too large"
                    ),
                    self._emergency_close(
                        short_connector, trading_pair, is_long=False,
                        amount=short_amount, reason=f"Hedge gap {gap_pct:.2%} too large"
                    )
                )
                raise Exception(f"Hedge gap {gap_pct:.2%} exceeds maximum 5%")

            self.logger().info(f"Hedge gap acceptable: {gap_pct:.2%}")

            # Phase 4: Track the position
            position_id = f"arb_{trading_pair}_{int(time.time())}"

            self.active_positions[position_id] = {
                'trading_pair': trading_pair,
                'long_exchange': long_exchange,
                'short_exchange': short_exchange,
                'long_order_id': long_order_id,
                'short_order_id': short_order_id,
                'long_amount': long_filled_amount,
                'short_amount': short_filled_amount,
                'notional_amount': edge.notional_amount,
                'expected_edge': edge.total_edge,
                'entry_time': time.time(),
                'edge_decomposition': edge
            }

            # Update risk trackers
            long_position = PositionInfo(
                exchange=long_exchange,
                subaccount=None,
                trading_pair=trading_pair,
                notional_amount=long_filled_amount,
                leverage=edge.leverage_long,
                side='long',
                timestamp=time.time(),
                order_ids=[long_order_id]
            )

            short_position = PositionInfo(
                exchange=short_exchange,
                subaccount=None,
                trading_pair=trading_pair,
                notional_amount=short_filled_amount,
                leverage=edge.leverage_short,
                side='short',
                timestamp=time.time(),
                order_ids=[short_order_id]
            )

            self.risk_manager.add_position(long_position)
            self.risk_manager.add_position(short_position)

            self.total_trades_executed += 1
            self.profitable_opportunities_taken += 1

            self.logger().info(f"✅ Arbitrage position {position_id} opened successfully")

        except Exception as e:
            self.logger().error(f"❌ Failed to execute arbitrage: {e}")
            # Position tracking not added since we failed or rolled back
            raise
    
    async def _place_order(self,
                         connector: ConnectorBase,
                         trading_pair: str,
                         is_buy: bool,
                         amount: Decimal,
                         price: Optional[Decimal] = None) -> str:
        """
        Place order on exchange with proper error handling.

        Args:
            connector: Exchange connector
            trading_pair: Trading pair symbol
            is_buy: True for buy, False for sell
            amount: Order amount in base currency
            price: Optional limit price (None for market orders)

        Returns:
            Order ID from exchange

        Raises:
            Exception: If order placement fails
        """
        order_type = OrderType.MARKET if price is None else OrderType.LIMIT

        try:
            if is_buy:
                order_id = connector.buy(
                    trading_pair=trading_pair,
                    amount=amount,
                    order_type=order_type,
                    price=price
                )
            else:
                order_id = connector.sell(
                    trading_pair=trading_pair,
                    amount=amount,
                    order_type=order_type,
                    price=price
                )

            self.logger().info(
                f"Placed {'BUY' if is_buy else 'SELL'} order {order_id} on {connector.name}: "
                f"{amount} {trading_pair} @ {'MARKET' if price is None else price}"
            )

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
                                  min_fill_ratio: Decimal = Decimal("0.95")) -> Tuple[bool, Decimal]:
        """
        Verify that an order was filled.

        Args:
            connector: Exchange connector
            order_id: Order ID to verify
            timeout_seconds: Maximum time to wait for fill
            min_fill_ratio: Minimum fill ratio to consider successful (0.95 = 95%)

        Returns:
            Tuple of (is_filled, filled_amount)
        """
        import asyncio

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                # Get order status from connector
                if hasattr(connector, 'get_order'):
                    order = connector.get_order(order_id)

                    if order is None:
                        await asyncio.sleep(0.5)
                        continue

                    # Check if order is filled
                    if hasattr(order, 'is_done') and order.is_done:
                        filled_amount = order.executed_amount_base if hasattr(order, 'executed_amount_base') else order.amount
                        fill_ratio = filled_amount / order.amount if order.amount > 0 else Decimal("0")

                        if fill_ratio >= min_fill_ratio:
                            self.logger().info(
                                f"Order {order_id} filled: {filled_amount}/{order.amount} ({fill_ratio:.1%})"
                            )
                            return True, filled_amount
                        else:
                            self.logger().warning(
                                f"Order {order_id} only partially filled: {fill_ratio:.1%}"
                            )
                            return False, filled_amount

                await asyncio.sleep(0.5)

            except Exception as e:
                self.logger().warning(f"Error checking order {order_id}: {e}")
                await asyncio.sleep(1)

        self.logger().error(f"Order {order_id} verification timeout after {timeout_seconds}s")
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
                price=None  # Market order for immediate execution
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
        long_amount = position_data.get('long_amount', position_data['notional_amount'])
        short_amount = position_data.get('short_amount', position_data['notional_amount'])

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
                    amount=long_amount
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
                    amount=short_amount
                )
                filled, filled_amount = await self._verify_order_filled(
                    short_connector, order_id, timeout_seconds=30
                )
                return filled, filled_amount

            # Execute both closes in parallel
            (long_closed, long_closed_amount), (short_closed, short_closed_amount) = await asyncio.gather(
                close_long(),
                close_short()
            )

            # Check results
            if not long_closed or not short_closed:
                self.logger().error(
                    f"Failed to close position {position_id} completely: "
                    f"long_closed={long_closed}, short_closed={short_closed}"
                )
                # Even if close failed, we remove from tracking to avoid infinite retries
                # Manual intervention may be needed

            # Calculate actual PnL
            # In real implementation, this would fetch actual funding payments received
            # For now, use expected edge as estimate
            estimated_pnl = position_data['expected_edge']
            position_duration_hours = (time.time() - position_data['entry_time']) / 3600

            self.total_funding_collected += estimated_pnl

            self.logger().info(
                f"✅ Position {position_id} closed: "
                f"long={long_closed_amount}, short={short_closed_amount}, "
                f"duration={position_duration_hours:.1f}h, estimated_pnl={estimated_pnl:.4f}"
            )

            # Remove from tracking
            del self.active_positions[position_id]

            # Remove from risk manager
            self.risk_manager.remove_position_by_exchange_pair(long_exchange, trading_pair)
            self.risk_manager.remove_position_by_exchange_pair(short_exchange, trading_pair)

        except Exception as e:
            self.logger().error(f"❌ Failed to close position {position_id}: {e}")
            # Still remove from tracking to avoid infinite retries
            if position_id in self.active_positions:
                del self.active_positions[position_id]
            raise
    
    def start(self):
        """Start the strategy."""
        super().start()
        
        # Start monitoring components
        asyncio.create_task(self.reconciliation_scheduler.start())
        asyncio.create_task(self.margin_monitor.run_monitoring_loop())
        
        self.logger().info("Funding arbitrage strategy started")
    
    def stop(self):
        """Stop the strategy."""
        # Stop monitoring
        asyncio.create_task(self.reconciliation_scheduler.stop())
        self.margin_monitor.stop_monitoring()
        
        # Close all positions
        for position_id in list(self.active_positions.keys()):
            asyncio.create_task(self._close_position(position_id, "Strategy stopping"))
        
        super().stop()
        self.logger().info("Funding arbitrage strategy stopped")
    
    def get_strategy_status(self) -> Dict:
        """Get comprehensive strategy status."""
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
        }