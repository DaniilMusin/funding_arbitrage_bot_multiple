# Funding Rate Arbitrage Bot

![Hummingbot](https://github.com/user-attachments/assets/3213d7f8-414b-4df8-8c1b-a0cd142a82d8)

[![License](https://img.shields.io/badge/License-Apache%202.0-informational.svg)](https://github.com/hummingbot/hummingbot/blob/master/LICENSE)
[![Twitter](https://img.shields.io/twitter/url?url=https://twitter.com/_hummingbot?style=social&label=_hummingbot)](https://twitter.com/_hummingbot)
[![Discord](https://img.shields.io/discord/530578568154054663?logo=discord&logoColor=white&style=flat-square)](https://discord.gg/hummingbot)

## Strategy Overview

This is a **funding rate arbitrage bot** built on top of [Hummingbot](https://github.com/hummingbot/hummingbot) that automatically captures funding rate differences between perpetual and spot markets. The bot identifies profitable funding rate spreads and executes market-neutral hedged positions to earn the funding payments.

### How It Works

The strategy employs a **delta-neutral hedging mechanism**:

1. **Long Perpetual + Short Spot**: When perpetual funding rates are positive (longs pay shorts), the bot goes long on perpetual futures and short on spot markets
2. **Short Perpetual + Long Spot**: When perpetual funding rates are negative (shorts pay longs), the bot goes short on perpetual futures and long on spot markets
3. **Cross-Perpetual Arbitrage**: The bot can also hedge between different perpetual exchanges when funding rate spreads are significant

The positions are sized to maintain market neutrality, capturing funding payments while minimizing directional price risk.

### Exchange Requirements

- **Multiple Sub-accounts**: Each exchange connector requires separate sub-accounts or API keys for isolated risk management
- **Margin Requirements**: Sufficient margin on perpetual exchanges to support leveraged positions
- **API Permissions**: Trading permissions enabled for both spot and derivatives APIs
- **Cross-margin Support**: Some exchanges require cross-margin mode for optimal hedging

### Risk Parameters

| Parameter | Description | Default Range |
|-----------|-------------|---------------|
| `min_funding_rate_profitability` | Minimum annualized funding rate spread to enter trades | 0.05% - 0.1% |
| `position_size_quote` | Trade size per connector in quote currency | Based on available margin |
| `leverage` | Leverage applied on derivative exchanges | 1-10x |
| `max_position_concentration` | Maximum % of portfolio in single asset | 20-50% |

## Quick Start

### 1. Environment Setup

Clone the repository and copy the environment template:

```bash
git clone <repository-url>
cd funding_arbitrage_bot_multiple
cp .env.example .env
```

### 2. Configure API Keys

Edit `.env` with your exchange API credentials:

```bash
# Bybit Perpetual
BYBIT_PERPETUAL_API_KEY=your_api_key
BYBIT_PERPETUAL_SECRET_KEY=your_secret_key

# Binance Spot
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key

# Add other exchanges as needed...
```

### 3. Configure Strategy Parameters

Edit `conf/funding_rate_arb.yml`:

```yaml
min_funding_rate_profitability: 0.0005  # 0.05% minimum spread
position_size_quote: 100                # $100 per position
leverage: 3                             # 3x leverage on perps
connectors:
  - bybit_perpetual
  - binance
tokens:
  - BTC-USDT
  - ETH-USDT
```

### 4. Start the Bot

```bash
# Using Docker Compose
docker-compose up -d

# Or directly
./start
```

### 5. Monitor and Verify

```bash
# Check exchange connections
./hb-check connections

# Monitor funding rates
./hb-check funding

# Check health status
curl http://localhost:5723/health/readiness
```

## Health Monitoring

The bot provides comprehensive health monitoring endpoints:

- **`/health/liveness`**: Basic process health check
- **`/health/readiness`**: Trading readiness (connections, margin, positions)
- **`/metrics`**: Detailed performance metrics

### Trading Safety Gate

- A strict guard blocks new orders until readiness is green: connectors healthy, margin OK, time sync OK, circuit breakers not tripped, and rate-limits available.
- Guard is enforced in `ScriptStrategyBase.buy/sell` and `ExecutorBase.place_order` and returns an error when blocked. Block reasons are logged and exported to metrics `hummingbot_trading_blocks_total{reason,...}`.
- Metrics also expose computed edge (`hummingbot_edge_value`) and time-to-next funding per exchange (`hummingbot_funding_time_to_next_seconds`).

## Limitations and Risks

### ⚠️ Risk Factors

1. **Execution Risk**: Delayed order execution can result in adverse price movements during position establishment
2. **Funding Rate Volatility**: Funding rates can change rapidly, affecting profitability calculations
3. **Exchange Risk**: Potential for exchange downtime, API rate limits, or account restrictions
4. **Counterparty Risk**: Risk of exchange insolvency or withdrawal restrictions
5. **Liquidation Risk**: Insufficient margin on leveraged positions during high volatility

### 🔒 Operational Limitations

- **Minimum Position Sizes**: Each exchange has minimum order size requirements
- **API Rate Limits**: Frequent position adjustments may hit exchange rate limits
- **Funding Frequency**: Most exchanges calculate funding every 8 hours, limiting strategy frequency
- **Cross-Exchange Latency**: Network delays between exchanges can impact execution timing
- **Regulatory Risk**: Potential for regulatory changes affecting perpetual futures trading

### 💡 Best Practices

- Start with small position sizes to test the strategy
- Monitor positions closely during high volatility periods
- Maintain adequate margin buffers on all exchanges
- Regularly review and adjust risk parameters
- Use separate sub-accounts for risk isolation

## Configuration

### Strategy Parameters

The main configuration file is `conf/funding_rate_arb.yml`:

| Key | Description | Example |
|-----|-------------|---------|
| `min_funding_rate_profitability` | Minimum annualized funding rate difference | `0.0005` (0.05%) |
| `position_size_quote` | Trade size per connector in quote currency | `100` ($100) |
| `leverage` | Leverage applied on derivative exchanges | `3` (3x leverage) |
| `connectors` | List of exchange connectors | `[bybit_perpetual, binance]` |
| `tokens` | Perpetual pairs to monitor and trade | `[BTC-USDT, ETH-USDT]` |

### Database Setup

The bot uses PostgreSQL for data storage. The Docker environment automatically sets up the database:

```bash
# For fresh installations, migrations run automatically
docker-compose up -d

# For existing databases, run migrations manually:
docker compose exec postgres psql -U postgres -d postgres -f db/002_add_funding_rates_raw.sql
```

## Development and Testing

### Exchange Connection Testing

Use the unified CLI tool to verify exchange connectivity:

```bash
# Test all configured exchanges
./hb-check connections

# Test specific exchange
./hb-check connections --exchange bybit_perpetual

# Check latency
./hb-check latency

# Monitor funding rates
./hb-check funding --pair BTC-USDT
```

### Contributing

This project is based on the open-source Hummingbot framework. For contributions:

1. Review the [contributing guidelines](./CONTRIBUTING.md)
2. Follow Hummingbot's governance process for significant changes
3. Test thoroughly with paper trading before live implementation

## Architecture

- Upstream `hummingbot/` is a read-only submodule. Do not modify code inside this path.
- Custom code must live under:
  - `strategies/` — strategy implementations
  - `adapters/` — exchange/broker abstractions and wrappers
  - `services/` — long-lived services (risk, readiness, observability adapters)
- Entry points are exposed via `console_scripts`.

## License

Licensed under [Apache 2.0](./LICENSE). This project is not affiliated with the Hummingbot Foundation.

## Related Resources

- [Hummingbot Documentation](https://hummingbot.org)
- [Exchange Setup Guide](./SETUP_INSTRUCTIONS.md)
- [Troubleshooting Guide](./README_EXCHANGE_CHECK.md)
- [Hummingbot Discord](https://discord.gg/hummingbot)

## Documentation (MkDocs)

Local preview:

```bash
pip install mkdocs mkdocs-material
mkdocs serve
```

Docs live under `docs/` with sections: Запуск, Риски, Диагностика, Runbooks.

## hb-check Reports

Now supports saving artifacts:

```bash
./hb-check connections --format=md --output-dir=./reports
./hb-check connections --format=json --output-dir=./reports
```

Artifacts are stored under `reports/YYYY-MM-DD/`.