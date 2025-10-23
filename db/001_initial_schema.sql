-- Initial database schema for Hummingbot trading analytics
-- Version: 1.0.0
-- Created: 2024-01-15

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Trades table for recording all trade executions
CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    amount DECIMAL(24,12) NOT NULL,
    price DECIMAL(24,12) NOT NULL,
    fee DECIMAL(24,12) DEFAULT 0,
    fee_currency VARCHAR(10),
    order_id VARCHAR(100),
    strategy VARCHAR(50),
    executed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trades_exchange_pair (exchange, trading_pair),
    INDEX idx_trades_executed_at (executed_at),
    INDEX idx_trades_strategy (strategy)
);

-- Orders table for order lifecycle tracking
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_order_id VARCHAR(100) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    order_type VARCHAR(20) NOT NULL,
    amount DECIMAL(24,12) NOT NULL,
    price DECIMAL(24,12),
    filled_amount DECIMAL(24,12) DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    strategy VARCHAR(50),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_client_order (client_order_id, exchange),
    INDEX idx_orders_exchange_pair (exchange, trading_pair),
    INDEX idx_orders_status (status),
    INDEX idx_orders_strategy (strategy)
);

-- Funding rates table (enhanced from existing)
CREATE TABLE IF NOT EXISTS funding_rates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    funding_rate DECIMAL(18,8) NOT NULL,
    predicted_rate DECIMAL(18,8),
    mark_price DECIMAL(24,12),
    index_price DECIMAL(24,12),
    open_interest DECIMAL(24,12),
    funding_time TIMESTAMP NOT NULL,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_funding_rate (exchange, trading_pair, funding_time),
    INDEX idx_funding_exchange_pair (exchange, trading_pair),
    INDEX idx_funding_time (funding_time)
);

-- Positions table for position tracking
CREATE TABLE IF NOT EXISTS positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT', 'BOTH')),
    amount DECIMAL(24,12) NOT NULL,
    entry_price DECIMAL(24,12) NOT NULL,
    mark_price DECIMAL(24,12),
    unrealized_pnl DECIMAL(24,12),
    leverage DECIMAL(8,2),
    margin DECIMAL(24,12),
    strategy VARCHAR(50),
    snapshot_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_positions_exchange_pair (exchange, trading_pair),
    INDEX idx_positions_snapshot_time (snapshot_time),
    INDEX idx_positions_strategy (strategy)
);

-- Balance snapshots for portfolio tracking
CREATE TABLE IF NOT EXISTS balance_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    currency VARCHAR(20) NOT NULL,
    total_balance DECIMAL(24,12) NOT NULL,
    available_balance DECIMAL(24,12) NOT NULL,
    locked_balance DECIMAL(24,12) DEFAULT 0,
    usd_value DECIMAL(24,12),
    strategy VARCHAR(50),
    snapshot_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_balance_exchange_currency (exchange, currency),
    INDEX idx_balance_snapshot_time (snapshot_time),
    INDEX idx_balance_strategy (strategy)
);

-- Market data snapshots for order book analysis
CREATE TABLE IF NOT EXISTS market_data_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    mid_price DECIMAL(24,12) NOT NULL,
    bid_price DECIMAL(24,12) NOT NULL,
    ask_price DECIMAL(24,12) NOT NULL,
    spread_bps DECIMAL(8,4) NOT NULL,
    bid_volume DECIMAL(24,12),
    ask_volume DECIMAL(24,12),
    volume_24h DECIMAL(24,12),
    snapshot_time TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_market_exchange_pair (exchange, trading_pair),
    INDEX idx_market_snapshot_time (snapshot_time)
);

-- Strategy performance metrics
CREATE TABLE IF NOT EXISTS strategy_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(24,12) NOT NULL,
    metric_unit VARCHAR(20),
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_metrics_strategy (strategy),
    INDEX idx_metrics_period (period_start, period_end)
);

-- Events table for system events and errors
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message TEXT NOT NULL,
    details JSON,
    strategy VARCHAR(50),
    exchange VARCHAR(50),
    occurred_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_events_type (event_type),
    INDEX idx_events_severity (severity),
    INDEX idx_events_occurred_at (occurred_at),
    INDEX idx_events_strategy (strategy)
);

-- Hedge operations tracking
CREATE TABLE IF NOT EXISTS hedge_operations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    operation_type VARCHAR(20) NOT NULL CHECK (operation_type IN ('HEDGE', 'REBALANCE', 'LIQUIDATION')),
    total_exposure DECIMAL(24,12) NOT NULL,
    target_exposure DECIMAL(24,12) NOT NULL,
    hedge_amount DECIMAL(24,12) NOT NULL,
    hedge_side VARCHAR(4) NOT NULL CHECK (hedge_side IN ('BUY', 'SELL')),
    hedge_price DECIMAL(24,12) NOT NULL,
    slippage DECIMAL(8,6),
    strategy VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    trading_pair VARCHAR(50) NOT NULL,
    execution_time_ms INTEGER,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    executed_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hedge_strategy (strategy),
    INDEX idx_hedge_executed_at (executed_at),
    INDEX idx_hedge_status (status)
);

-- Risk metrics tracking
CREATE TABLE IF NOT EXISTS risk_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy VARCHAR(50) NOT NULL,
    total_exposure_usd DECIMAL(24,12) NOT NULL,
    max_drawdown DECIMAL(8,6),
    var_95 DECIMAL(24,12),
    var_99 DECIMAL(24,12),
    sharpe_ratio DECIMAL(8,6),
    sortino_ratio DECIMAL(8,6),
    max_leverage DECIMAL(8,2),
    concentration_risk DECIMAL(8,6),
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    INDEX idx_risk_strategy (strategy),
    INDEX idx_risk_calculated_at (calculated_at)
);