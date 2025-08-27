#!/bin/bash

# Funding Arbitrage Bot Installation Script
# This script sets up the bot with the upstream Hummingbot as a submodule

set -e

echo "🚀 Setting up Funding Arbitrage Bot..."

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: This script must be run from within a git repository"
    exit 1
fi

# Initialize and update submodules
echo "📦 Initializing Hummingbot submodule..."
git submodule init
git submodule update --init --recursive

# Pin to a specific Hummingbot version (latest stable)
echo "📌 Pinning Hummingbot to latest stable version..."
cd hummingbot-upstream

# Get the latest release tag
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "development")
if [ "$LATEST_TAG" != "development" ]; then
    echo "🏷️  Using Hummingbot version: $LATEST_TAG"
    git checkout $LATEST_TAG
else
    echo "⚠️  Warning: No release tags found, using development branch"
fi

cd ..

# Install Hummingbot core dependencies
echo "📚 Installing Hummingbot core..."
cd hummingbot-upstream
pip install -e .
cd ..

# Install our custom package
echo "🎯 Installing custom strategies and extensions..."
pip install -e .

# Set up symbolic links for easier access
echo "🔗 Setting up symbolic links..."
if [ ! -L "hummingbot" ]; then
    ln -s hummingbot-upstream/hummingbot hummingbot
fi

# Create directories if they don't exist
mkdir -p logs conf data

# Copy configuration templates
echo "📝 Setting up configuration templates..."
if [ ! -f "conf/funding_rate_arb.yml" ]; then
    cat > conf/funding_rate_arb.yml << 'EOF'
# Funding Rate Arbitrage Strategy Configuration

# Minimum annualized funding rate difference to enter trades (0.05%)
min_funding_rate_profitability: 0.0005

# Trade size per connector in quote currency
position_size_quote: 100

# Leverage applied on derivative exchanges
leverage: 3

# List of exchange connectors to use
connectors:
  - bybit_perpetual
  - binance

# Perpetual pairs to monitor and trade
tokens:
  - BTC-USDT
  - ETH-USDT

# Take profit threshold (as multiple of position size)
profitability_to_take_profit: 0.02
EOF
fi

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Configure your API keys in .env file"
echo "2. Adjust strategy parameters in conf/funding_rate_arb.yml"
echo "3. Run './start' to begin trading"
echo ""
echo "📚 Documentation: Check README.md for detailed setup instructions"