#!/usr/bin/env python3
"""
Test script for funding rate arbitrage bot
"""

import asyncio
import aiohttp
import time
from decimal import Decimal


async def test_exchanges():
    """Test basic exchange connectivity"""
    print("=== Testing Exchange Connectivity ===")
    
    exchanges = {
        "OKX": "https://www.okx.com/api/v5/public/instruments?instType=SWAP",
        "Bybit": "https://api.bybit.com/v5/market/instruments-info?category=linear", 
        "BingX": "https://open-api.bingx.com/openApi/spot/v1/common/symbols",
        "Hyperliquid": "https://api.hyperliquid.xyz/info"
    }
    
    async with aiohttp.ClientSession() as session:
        for name, url in exchanges.items():
            try:
                print(f"Testing {name}...")
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        print(f"[OK] {name}: OK (status {response.status})")
                    else:
                        print(f"[FAIL] {name}: Failed (status {response.status})")
            except Exception as e:
                print(f"[ERROR] {name}: Error - {str(e)}")


async def test_config_loading():
    """Test configuration loading"""
    print("\n=== Testing Configuration Loading ===")
    
    try:
        import sys
        import os
        sys.path.insert(0, '.')
        
        # Test YAML config loading
        import yaml
        with open('conf/funding_rate_arb.yml', 'r') as f:
            config = yaml.safe_load(f)
        
        print("[OK] YAML config loaded successfully")
        print(f"  Min profitability: {config['min_funding_rate_profitability']}")
        print(f"  Position size: {config['position_size_quote']}")
        print(f"  Leverage: {config['leverage']}")
        print(f"  Connectors: {config['connectors']}")
        print(f"  Tokens: {config['tokens']}")
        
    except Exception as e:
        print(f"[ERROR] Config loading failed: {str(e)}")


async def test_funding_rates():
    """Test funding rate fetching"""
    print("\n=== Testing Funding Rate Fetching ===")
    
    async with aiohttp.ClientSession() as session:
        # Test OKX funding rate
        try:
            url = "https://www.okx.com/api/v5/public/funding-rate?instId=BTC-USDT-SWAP"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('data'):
                        rate = float(data['data'][0]['fundingRate'])
                        print(f"[OK] OKX BTC funding rate: {rate:.6f} ({rate*100:.4f}%)")
                    else:
                        print("[FAIL] OKX: No funding rate data")
                else:
                    print(f"[FAIL] OKX: HTTP {response.status}")
        except Exception as e:
            print(f"[FAIL] OKX: {str(e)}")
        
        # Test Bybit funding rate
        try:
            url = "https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&limit=1"
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('result', {}).get('list'):
                        rate = float(data['result']['list'][0]['fundingRate'])
                        print(f"[OK] Bybit BTC funding rate: {rate:.6f} ({rate*100:.4f}%)")
                    else:
                        print("[FAIL] Bybit: No funding rate data")
                else:
                    print(f"[FAIL] Bybit: HTTP {response.status}")
        except Exception as e:
            print(f"[FAIL] Bybit: {str(e)}")


def calculate_arbitrage_example():
    """Calculate example arbitrage opportunity"""
    print("\n=== Arbitrage Calculation Example ===")
    
    # Example funding rates
    okx_rate = Decimal("0.0001")  # 0.01%
    bybit_rate = Decimal("-0.0005")  # -0.05%
    
    rate_diff = okx_rate - bybit_rate
    annual_rate = rate_diff * 365 * 3  # 3 funding payments per day
    
    print(f"OKX funding rate: {okx_rate:.4f} ({float(okx_rate)*100:.2f}%)")
    print(f"Bybit funding rate: {bybit_rate:.4f} ({float(bybit_rate)*100:.2f}%)")
    print(f"Rate difference: {rate_diff:.4f} ({float(rate_diff)*100:.2f}%)")
    print(f"Annualized profit: {annual_rate:.4f} ({float(annual_rate)*100:.1f}%)")
    
    # Check if profitable
    min_profitability = Decimal("0.0005")  # 0.05%
    if rate_diff > min_profitability:
        print(f"[OK] Arbitrage opportunity! (diff {float(rate_diff)*100:.2f}% > min {float(min_profitability)*100:.2f}%)")
        print("  Strategy: Long on Bybit (pay negative rate), Short on OKX (receive positive rate)")
    else:
        print(f"[FAIL] No arbitrage opportunity (diff {float(rate_diff)*100:.2f}% < min {float(min_profitability)*100:.2f}%)")


async def main():
    """Run all tests"""
    print("Funding Rate Arbitrage Bot - Test Suite")
    print("=" * 50)
    
    await test_exchanges()
    await test_config_loading()
    await test_funding_rates()
    calculate_arbitrage_example()
    
    print("\n" + "=" * 50)
    print("Test suite completed!")


if __name__ == "__main__":
    asyncio.run(main())