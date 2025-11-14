#!/usr/bin/env python3
"""
Test OKX and Hyperliquid connections for funding arbitrage bot
This script verifies that both exchanges are properly configured and accessible
"""

import asyncio
import os
import sys
from decimal import Decimal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_okx_connection():
    """Test OKX Perpetual connection"""
    print("\n" + "=" * 80)
    print("Testing OKX Perpetual Connection")
    print("=" * 80)

    # Get credentials from environment
    api_key = os.getenv('OKX_PERPETUAL_API_KEY')
    secret_key = os.getenv('OKX_PERPETUAL_SECRET_KEY')
    passphrase = os.getenv('OKX_PERPETUAL_PASSPHRASE')

    if not all([api_key, secret_key, passphrase]):
        print("❌ ERROR: Missing OKX credentials!")
        print("   Please set: OKX_PERPETUAL_API_KEY, OKX_PERPETUAL_SECRET_KEY, OKX_PERPETUAL_PASSPHRASE")
        return False

    print(f"✓ API Key: {api_key[:10]}...{api_key[-10:]}")
    print(f"✓ Secret Key: {secret_key[:10]}...{secret_key[-10:]}")
    print(f"✓ Passphrase: {'*' * len(passphrase)}")

    try:
        from hummingbot.client.config.config_helpers import ClientConfigAdapter
        from hummingbot.client.config.client_config_map import ClientConfigMap
        from hummingbot.connector.derivative.okx_perpetual.okx_perpetual_derivative import OkxPerpetualDerivative

        # Create connector
        client_config = ClientConfigAdapter(ClientConfigMap())
        connector = OkxPerpetualDerivative(
            client_config_map=client_config,
            okx_perpetual_api_key=api_key,
            okx_perpetual_secret_key=secret_key,
            okx_perpetual_passphrase=passphrase,
            trading_pairs=['BTC-USDT', 'ETH-USDT'],
            trading_required=True
        )

        print("\n📊 Testing OKX Features:")

        # Test 1: Get trading pairs
        print("\n1. Fetching trading pairs...")
        await connector._update_trading_rules()
        if connector.trading_rules:
            print(f"   ✅ Found {len(connector.trading_rules)} trading pairs")
            # Show BTC and ETH pairs
            for pair in ['BTC-USDT', 'ETH-USDT']:
                if pair in connector.trading_rules:
                    rule = connector.trading_rules[pair]
                    print(f"   • {pair}: Min order size = {rule.min_order_size}")
        else:
            print("   ⚠️  No trading pairs found")
            return False

        # Test 2: Get funding info
        print("\n2. Fetching funding rates...")
        for trading_pair in ['BTC-USDT', 'ETH-USDT']:
            try:
                funding_info = await connector._order_book_tracker.data_source.get_funding_info(trading_pair)
                print(f"   ✅ {trading_pair}:")
                print(f"      • Funding Rate: {funding_info.rate * 100:.4f}%")
                print(f"      • Mark Price: ${funding_info.mark_price:,.2f}")
                print(f"      • Index Price: ${funding_info.index_price:,.2f}")
            except Exception as e:
                print(f"   ❌ Failed to get funding info for {trading_pair}: {e}")
                return False

        # Test 3: Get account balance (requires valid credentials)
        print("\n3. Fetching account balances...")
        try:
            await connector._update_balances()
            balances = connector.available_balances
            if balances:
                print("   ✅ Account balances:")
                for currency, amount in balances.items():
                    if amount > 0:
                        print(f"      • {currency}: {amount}")
            else:
                print("   ⚠️  No balances found (may need to deposit funds)")
        except Exception as e:
            print(f"   ❌ Failed to get balances: {e}")
            print("   Note: This may indicate invalid API credentials")
            return False

        print("\n✅ OKX Perpetual connection test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ OKX connection test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_hyperliquid_connection():
    """Test Hyperliquid Perpetual connection"""
    print("\n" + "=" * 80)
    print("Testing Hyperliquid Perpetual Connection")
    print("=" * 80)

    # Get credentials from environment
    api_key = os.getenv('HYPERLIQUID_PERPETUAL_API_KEY')
    secret_key = os.getenv('HYPERLIQUID_PERPETUAL_SECRET_KEY')

    if not all([api_key, secret_key]):
        print("❌ ERROR: Missing Hyperliquid credentials!")
        print("   Please set: HYPERLIQUID_PERPETUAL_API_KEY (wallet address)")
        print("   and HYPERLIQUID_PERPETUAL_SECRET_KEY (private key)")
        return False

    print(f"✓ Wallet Address: {api_key[:10]}...{api_key[-10:]}")
    print(f"✓ Private Key: {secret_key[:10]}...{secret_key[-10:]}")

    try:
        from hummingbot.client.config.config_helpers import ClientConfigAdapter
        from hummingbot.client.config.client_config_map import ClientConfigMap
        from hummingbot.connector.derivative.hyperliquid_perpetual.hyperliquid_perpetual_derivative import HyperliquidPerpetualDerivative

        # Create connector
        client_config = ClientConfigAdapter(ClientConfigMap())
        connector = HyperliquidPerpetualDerivative(
            client_config_map=client_config,
            hyperliquid_perpetual_api_key=api_key,
            hyperliquid_perpetual_api_secret=secret_key,
            trading_pairs=['BTC-USD', 'ETH-USD'],
            trading_required=True
        )

        print("\n📊 Testing Hyperliquid Features:")

        # Test 1: Get trading pairs
        print("\n1. Fetching trading pairs...")
        await connector._update_trading_rules()
        if connector.trading_rules:
            print(f"   ✅ Found {len(connector.trading_rules)} trading pairs")
            # Show BTC and ETH pairs
            for pair in ['BTC-USD', 'ETH-USD']:
                if pair in connector.trading_rules:
                    rule = connector.trading_rules[pair]
                    print(f"   • {pair}: Min order size = {rule.min_order_size}")
        else:
            print("   ⚠️  No trading pairs found")
            return False

        # Test 2: Get funding info
        print("\n2. Fetching funding rates...")
        for trading_pair in ['BTC-USD', 'ETH-USD']:
            try:
                funding_info = await connector._order_book_tracker.data_source.get_funding_info(trading_pair)
                print(f"   ✅ {trading_pair}:")
                print(f"      • Funding Rate: {funding_info.rate * 100:.4f}%")
                print(f"      • Mark Price: ${funding_info.mark_price:,.2f}")
                print(f"      • Index Price: ${funding_info.index_price:,.2f}")
            except Exception as e:
                print(f"   ❌ Failed to get funding info for {trading_pair}: {e}")
                return False

        # Test 3: Get account balance
        print("\n3. Fetching account balances...")
        try:
            await connector._update_balances()
            balances = connector.available_balances
            if balances:
                print("   ✅ Account balances:")
                for currency, amount in balances.items():
                    if amount > 0:
                        print(f"      • {currency}: {amount}")
            else:
                print("   ⚠️  No balances found (may need to deposit funds)")
        except Exception as e:
            print(f"   ❌ Failed to get balances: {e}")
            print("   Note: This may indicate invalid API credentials")
            return False

        print("\n✅ Hyperliquid Perpetual connection test PASSED!")
        return True

    except Exception as e:
        print(f"\n❌ Hyperliquid connection test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_funding_arbitrage_opportunity():
    """Test for funding rate arbitrage opportunities"""
    print("\n" + "=" * 80)
    print("Checking for Funding Arbitrage Opportunities")
    print("=" * 80)

    # This is a simplified test - full bot would do more sophisticated analysis
    print("\n⚠️  Note: This is a simplified check. The actual bot performs more sophisticated analysis.")
    print("\nFor a real arbitrage opportunity, you need:")
    print("  • Significant funding rate difference (e.g., > 0.05% per 8 hours)")
    print("  • Sufficient liquidity on both exchanges")
    print("  • Account for trading fees and slippage")
    print("  • Consider funding payment schedule differences")

    return True


async def main():
    """Main test function"""
    print("\n" + "=" * 80)
    print("OKX + HYPERLIQUID FUNDING ARBITRAGE BOT - CONNECTION TEST")
    print("=" * 80)

    # Load environment variables from .env file if it exists
    try:
        from dotenv import load_dotenv
        if os.path.exists('.env'):
            load_dotenv()
            print("✓ Loaded .env file")
        else:
            print("⚠️  No .env file found - using system environment variables")
    except ImportError:
        print("⚠️  python-dotenv not installed - using system environment variables")

    results = []

    # Test OKX
    results.append(await test_okx_connection())

    # Test Hyperliquid
    results.append(await test_hyperliquid_connection())

    # Check for opportunities
    results.append(await test_funding_arbitrage_opportunity())

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    if all(results):
        print("\n✅ ALL TESTS PASSED!")
        print("\nYou're ready to run the funding arbitrage bot.")
        print("\nNext steps:")
        print("  1. Review and adjust configuration in conf/funding_rate_arb.yml")
        print("  2. Start with paper trading mode to test the strategy")
        print("  3. Monitor the bot carefully for the first few hours")
        print("  4. Gradually increase position sizes as you gain confidence")
    else:
        print("\n❌ SOME TESTS FAILED")
        print("\nPlease fix the issues above before running the bot.")
        print("\nCommon issues:")
        print("  • Invalid API credentials")
        print("  • API keys don't have required permissions")
        print("  • Network connectivity issues")
        print("  • Exchange API is down or under maintenance")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
