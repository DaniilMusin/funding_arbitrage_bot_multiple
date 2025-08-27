# Funding Rate Arbitrage Bot

![Hummingbot](https://github.com/user-attachments/assets/3213d7f8-414b-4df8-8c1b-a0cd142a82d8)

[![License](https://img.shields.io/badge/License-Apache%202.0-informational.svg)](https://github.com/hummingbot/hummingbot/blob/master/LICENSE)
[![Twitter](https://img.shields.io/twitter/url?url=https://twitter.com/_hummingbot?style=social&label=_hummingbot)](https://twitter.com/_hummingbot)
[![Discord](https://img.shields.io/discord/530578568154054663?logo=discord&logoColor=white&style=flat-square)](https://discord.gg/hummingbot)

## 🏗️ Modular Architecture

This project uses a **modular architecture** that decouples custom code from the upstream Hummingbot codebase, making updates and maintenance much easier:

```
funding-arbitrage-bot/
├── hummingbot-upstream/     # Git submodule → upstream Hummingbot
├── strategies/              # Custom trading strategies
│   └── funding_arbitrage/   # Funding rate arbitrage strategy
├── adapters/                # Core extensions and customizations
│   └── core_ext/           # Logging, state sync, throttling
├── services/                # Additional services and controllers
│   └── controllers/        # Custom trading controllers
├── scripts/                 # Utility and standalone scripts
└── conf/                   # Configuration files
```

### Benefits of This Architecture

- ✅ **Easy Updates**: Upstream Hummingbot is a git submodule, updates are simple
- ✅ **Clean Separation**: Custom code is isolated from vendor code
- ✅ **Modular Design**: Each component has a clear responsibility
- ✅ **Plugin System**: Strategies work as plugins to the core system
- ✅ **No Merge Conflicts**: Your customizations never conflict with upstream changes

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

Clone the repository and set up the modular architecture:

```bash
git clone <repository-url>
cd funding-arbitrage-bot

# Set up the modular architecture with Hummingbot submodule
./install.sh
```

### 2. Configure API Keys

Create and edit `.env` with your exchange API credentials:

```bash
cp .env.example .env
# Edit .env file with your API keys
```

Example `.env`:
```bash
# Bybit Perpetual
BYBIT_PERPETUAL_API_KEY=your_api_key
BYBIT_PERPETUAL_SECRET_KEY=your_secret_key

# Binance Spot
BINANCE_API_KEY=your_api_key
BINANCE_SECRET_KEY=your_secret_key

# Optional: Enable state synchronization
ENABLE_STATE_SYNC=true
STATE_SYNC_DSN=postgresql://localhost/postgres
```

### 3. Configure Strategy Parameters

The installation script creates `conf/funding_rate_arb.yml` with default settings:

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
# Start with the new modular architecture
./start

# Or run a specific strategy file
./start -f v2_funding_rate_arb.py

# Using Docker Compose (if preferred)
docker-compose up -d
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

### 6. Updating Hummingbot

To update to the latest Hummingbot version:

```bash
# Update the upstream submodule
./update_upstream.sh

# Commit the update
git add hummingbot-upstream
git commit -m "Update Hummingbot to latest version"
```

## Health Monitoring

The bot provides comprehensive health monitoring endpoints:

- **`/health/liveness`**: Basic process health check
- **`/health/readiness`**: Trading readiness (connections, margin, positions)
- **`/metrics`**: Detailed performance metrics

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

## Architecture Deep Dive

### Directory Structure

```
funding-arbitrage-bot/
├── hummingbot-upstream/              # Git submodule to upstream Hummingbot
│   ├── hummingbot/                   # Core Hummingbot package
│   ├── bin/                          # Hummingbot executables
│   └── ...                          # Other upstream files
├── strategies/                       # Custom trading strategies (plugins)
│   └── funding_arbitrage/            
│       ├── __init__.py               # Plugin exports
│       └── v2_funding_rate_arb.py    # Main funding arbitrage strategy
├── adapters/                         # Core functionality extensions
│   └── core_ext/                     
│       ├── __init__.py               # Adapter exports  
│       ├── logging_conf.py           # Structured logging setup
│       ├── state_sync.py             # PostgreSQL state synchronization
│       └── throttle.py               # Redis-based rate limiting
├── services/                         # Additional services and controllers
│   └── controllers/                  # Custom trading controllers
│       ├── directional_trading/      # Directional strategies
│       ├── market_making/            # Market making controllers
│       └── generic/                  # Generic controllers
├── scripts/                          # Standalone scripts and utilities
├── conf/                            # Configuration files
├── install.sh                       # Setup script for submodule architecture
├── update_upstream.sh               # Script to update Hummingbot upstream
└── start                           # Modified startup script
```

### Benefits of the Modular Architecture

1. **Upstream Isolation**: The entire Hummingbot codebase is contained in `hummingbot-upstream/` as a git submodule
2. **Clean Updates**: Update Hummingbot by running `./update_upstream.sh` - no merge conflicts
3. **Plugin System**: Custom strategies in `strategies/` work as plugins
4. **Adapter Pattern**: Core extensions in `adapters/` modify behavior without patching upstream
5. **Service Separation**: Additional services in `services/` are clearly separated from core logic

### Update Process

When a new Hummingbot version is released:

```bash
# Update to latest upstream version
./update_upstream.sh

# Test that everything still works
./start

# Commit the submodule update
git add hummingbot-upstream
git commit -m "Update Hummingbot to v1.x.x"
```

This process ensures your customizations remain intact while staying current with upstream improvements.

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

## License

Licensed under [Apache 2.0](./LICENSE). This project is not affiliated with the Hummingbot Foundation.

## Related Resources

- [Hummingbot Documentation](https://hummingbot.org)
- [Exchange Setup Guide](./SETUP_INSTRUCTIONS.md)
- [Troubleshooting Guide](./README_EXCHANGE_CHECK.md)
- [Hummingbot Discord](https://discord.gg/hummingbot)