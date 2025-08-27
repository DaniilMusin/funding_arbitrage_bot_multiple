-- Performance optimization indexes
-- Version: 1.1.0
-- Created: 2024-01-15

-- Composite indexes for common query patterns

-- Trades performance indexes
CREATE INDEX IF NOT EXISTS idx_trades_strategy_time ON trades (strategy, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_exchange_pair_time ON trades (exchange, trading_pair, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_pnl_analysis ON trades (trading_pair, side, executed_at DESC);

-- Orders performance indexes  
CREATE INDEX IF NOT EXISTS idx_orders_strategy_status ON orders (strategy, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_exchange_active ON orders (exchange, status) WHERE status IN ('PENDING', 'PARTIALLY_FILLED');

-- Funding rates analysis indexes
CREATE INDEX IF NOT EXISTS idx_funding_rates_analysis ON funding_rates (trading_pair, funding_time DESC);
CREATE INDEX IF NOT EXISTS idx_funding_rates_arb ON funding_rates (funding_time DESC, funding_rate DESC);

-- Position tracking indexes
CREATE INDEX IF NOT EXISTS idx_positions_current ON positions (exchange, trading_pair, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_positions_pnl ON positions (strategy, snapshot_time DESC, unrealized_pnl DESC);

-- Balance tracking indexes
CREATE INDEX IF NOT EXISTS idx_balance_portfolio ON balance_snapshots (strategy, snapshot_time DESC, usd_value DESC);
CREATE INDEX IF NOT EXISTS idx_balance_currency_time ON balance_snapshots (currency, snapshot_time DESC);

-- Market data indexes
CREATE INDEX IF NOT EXISTS idx_market_data_spread ON market_data_snapshots (trading_pair, spread_bps DESC, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_volume ON market_data_snapshots (trading_pair, volume_24h DESC, snapshot_time DESC);

-- Hedge operations indexes
CREATE INDEX IF NOT EXISTS idx_hedge_performance ON hedge_operations (strategy, executed_at DESC, execution_time_ms);
CREATE INDEX IF NOT EXISTS idx_hedge_analysis ON hedge_operations (trading_pair, operation_type, executed_at DESC);

-- Events indexes for monitoring
CREATE INDEX IF NOT EXISTS idx_events_monitoring ON events (severity, occurred_at DESC) WHERE severity IN ('ERROR', 'CRITICAL');
CREATE INDEX IF NOT EXISTS idx_events_strategy_errors ON events (strategy, severity, occurred_at DESC) WHERE severity IN ('ERROR', 'CRITICAL');

-- Risk metrics indexes
CREATE INDEX IF NOT EXISTS idx_risk_latest ON risk_metrics (strategy, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_drawdown ON risk_metrics (max_drawdown DESC, calculated_at DESC);

-- Partitioning preparation (for large datasets)
-- Note: These would be created based on data volume requirements

-- Drop unused indexes from old schema if they exist
DROP INDEX IF EXISTS idx_trades_exchange_pair;
DROP INDEX IF EXISTS idx_orders_exchange_pair;
DROP INDEX IF EXISTS idx_funding_exchange_pair;