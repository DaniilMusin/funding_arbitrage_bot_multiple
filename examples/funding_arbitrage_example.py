"""
Example usage of the comprehensive funding arbitrage strategy.
Demonstrates all key features and components.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Dict
import time

# Mock exchange connector for demonstration
class MockExchangeConnector:
    def __init__(self, name: str):
        self.name = name
        self.funding_rates = {
            'BTC-USDT': Decimal('0.0001'),  # 0.01% 
            'ETH-USDT': Decimal('0.0002'),
        }
    
    async def get_funding_info(self, trading_pair: str):
        from hummingbot.core.data_type.funding_info import FundingInfo
        
        rate = self.funding_rates.get(trading_pair, Decimal('0'))
        # Simulate some variation
        if self.name == 'bybit':
            rate *= Decimal('1.5')  # Higher funding rate
        elif self.name == 'okx':
            rate *= Decimal('0.8')  # Lower funding rate
            
        return FundingInfo(
            trading_pair=trading_pair,
            index_price=Decimal('50000'),
            mark_price=Decimal('50000'),
            next_funding_utc_timestamp=int(time.time() + 3600),  # 1 hour from now
            rate=rate
        )


async def main():
    """Demonstrate the funding arbitrage strategy."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    # Import strategy components
    from hummingbot.strategy.funding_arbitrage import (
        FundingArbitrageStrategy, 
        FundingArbitrageConfig,
        EdgeCalculator,
        FundingScheduler,
        RiskManager,
        MarginMonitor
    )
    
    logger.info("🚀 Starting Funding Arbitrage Strategy Demo")
    
    # 1. Create mock exchanges
    exchanges = {
        'binance': MockExchangeConnector('binance'),
        'bybit': MockExchangeConnector('bybit'), 
        'okx': MockExchangeConnector('okx'),
    }
    
    # 2. Configure strategy
    config = FundingArbitrageConfig(
        min_edge_required=Decimal("0.0005"),  # 0.05% minimum edge
        max_notional_per_exchange=Decimal("10000"),  # $10k max per exchange
        max_total_notional=Decimal("50000"),  # $50k total max
        max_leverage=Decimal("3"),  # Max 3x leverage
        auto_leverage_reduction=True,
        auto_position_reconciliation=True,
    )
    
    trading_pairs = ['BTC-USDT', 'ETH-USDT']
    
    # 3. Initialize strategy
    strategy = FundingArbitrageStrategy(
        exchanges=exchanges,
        config=config,
        trading_pairs=trading_pairs
    )
    
    logger.info("✅ Strategy initialized")
    
    # 4. Demonstrate edge calculation
    logger.info("\n📊 Edge Calculation Demo")
    edge_calculator = EdgeCalculator(min_edge_required=Decimal("0.0005"))
    
    edge = edge_calculator.calculate_edge(
        trading_pair='BTC-USDT',
        exchange_long='binance',
        exchange_short='bybit',
        funding_rate_long=Decimal('0.0001'),  # 0.01%
        funding_rate_short=Decimal('0.0015'),  # 0.15% 
        notional_amount=Decimal('5000'),
        fees_config={
            'binance': {'maker': Decimal('0.0001'), 'taker': Decimal('0.0004')},
            'bybit': {'maker': Decimal('0.0002'), 'taker': Decimal('0.0006')}
        },
        borrow_rates={'BTC': Decimal('0.0001'), 'USDT': Decimal('0.00005')},
        slippage_estimates={'binance': Decimal('0.0003'), 'bybit': Decimal('0.0005')}
    )
    
    logger.info("Edge Decomposition:")
    for key, value in edge.to_display_dict().items():
        logger.info(f"  {key}: {value}")
    
    # 5. Demonstrate funding scheduler
    logger.info("\n⏰ Funding Scheduler Demo")
    scheduler = FundingScheduler()
    
    status, minutes_to_settlement = scheduler.get_settlement_status(['binance', 'bybit'])
    logger.info(f"Settlement status: {status.value}")
    logger.info(f"Minutes to settlement: {minutes_to_settlement}")
    
    should_open, reason = scheduler.should_open_position(['binance', 'bybit'])
    logger.info(f"Should open position: {should_open} ({reason})")
    
    # 6. Demonstrate risk management
    logger.info("\n🛡️ Risk Management Demo")
    risk_manager = RiskManager()
    
    # Check position limits
    can_open, violations, risk_level = risk_manager.check_position_limits(
        exchange='binance',
        subaccount=None,
        trading_pair='BTC-USDT',
        proposed_notional=Decimal('5000'),
        proposed_leverage=Decimal('2')
    )
    
    logger.info(f"Can open position: {can_open}")
    logger.info(f"Risk level: {risk_level.value}")
    if violations:
        logger.info(f"Violations: {violations}")
    
    # 7. Demonstrate margin monitoring
    logger.info("\n📈 Margin Monitoring Demo")
    margin_monitor = MarginMonitor(max_allowed_leverage=Decimal('5'))
    
    safe_leverage = margin_monitor.calculate_safe_leverage(
        exchange='binance',
        symbol='BTC-USDT', 
        notional=Decimal('10000')
    )
    logger.info(f"Safe leverage for BTC-USDT: {safe_leverage}")
    
    # 8. Simulate running the strategy
    logger.info("\n🔄 Strategy Simulation")
    
    # Start strategy components
    strategy.start()
    
    # Simulate a few ticks
    for i in range(3):
        logger.info(f"\n--- Tick {i+1} ---")
        await strategy.on_tick()
        
        # Show status
        status = strategy.get_strategy_status()
        logger.info(f"Active positions: {status['active_positions']}")
        logger.info(f"Total trades: {status['total_trades']}")
        logger.info(f"Opportunities skipped: {status['opportunities_skipped']}")
        
        await asyncio.sleep(1)  # Brief pause
    
    # 9. Show final status
    logger.info("\n📊 Final Strategy Status")
    final_status = strategy.get_strategy_status()
    
    for category, data in final_status.items():
        if isinstance(data, dict):
            logger.info(f"\n{category.upper()}:")
            for key, value in data.items():
                logger.info(f"  {key}: {value}")
        else:
            logger.info(f"{category}: {data}")
    
    # Stop strategy
    strategy.stop()
    logger.info("\n🏁 Strategy demo completed!")
    
    # 10. Performance insights
    logger.info("\n💡 Key Features Demonstrated:")
    logger.info("✅ Edge decomposition with transparent cost breakdown")
    logger.info("✅ Funding settlement timing with exchange-specific schedules")
    logger.info("✅ Multi-layered risk management with position limits")
    logger.info("✅ Automatic reconciliation of positions and balances")
    logger.info("✅ Margin monitoring with ADL protection")
    logger.info("✅ Market-specific logic with emergency safeguards")


if __name__ == "__main__":
    asyncio.run(main())