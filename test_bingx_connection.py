#!/usr/bin/env python3
"""
Test BingX connection with API keys
"""

import asyncio
import aiohttp
import time
import hmac
import hashlib
import json
from urllib.parse import urlencode


class BingXTester:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://open-api.bingx.com"
    
    def _sign(self, params_str):
        """Create signature for BingX API"""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            params_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def test_account_info(self):
        """Test getting account information"""
        print("\n=== Testing BingX Account Info ===")
        
        # Prepare request
        timestamp = str(int(time.time() * 1000))
        params = {
            'timestamp': timestamp
        }
        
        query_string = urlencode(params)
        signature = self._sign(query_string)
        params['signature'] = signature
        
        headers = {
            'X-BX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/openApi/spot/v1/account/balance"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    print(f"Status: {response.status}")
                    text = await response.text()
                    print(f"Response: {text}")
                    
                    if response.status == 200:
                        data = json.loads(text)
                        if data.get('code') == 0:
                            print("[OK] Account info retrieved successfully!")
                            balances = data.get('data', {}).get('balances', [])
                            for balance in balances[:5]:  # Show first 5 balances
                                if float(balance.get('free', 0)) > 0:
                                    print(f"  {balance['asset']}: {balance['free']} (available)")
                        else:
                            print(f"[ERROR] API Error: {data.get('msg', 'Unknown error')}")
                    else:
                        print(f"[ERROR] HTTP {response.status}: {text}")
        except Exception as e:
            print(f"[ERROR] Connection failed: {str(e)}")
    
    async def test_symbols(self):
        """Test getting trading symbols"""
        print("\n=== Testing BingX Symbols ===")
        
        url = f"{self.base_url}/openApi/spot/v1/common/symbols"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == 0:
                            symbols = data.get('data', {}).get('symbols', [])
                            btc_symbols = [s for s in symbols if 'BTC' in s['symbol']][:5]
                            print(f"[OK] Found {len(symbols)} symbols")
                            print("BTC pairs:")
                            for symbol in btc_symbols:
                                print(f"  {symbol['symbol']} - Status: {symbol['status']}")
                        else:
                            print(f"[ERROR] API Error: {data.get('msg', 'Unknown error')}")
                    else:
                        print(f"[ERROR] HTTP {response.status}")
        except Exception as e:
            print(f"[ERROR] Connection failed: {str(e)}")
    
    async def test_perpetual_positions(self):
        """Test getting perpetual positions"""
        print("\n=== Testing BingX Perpetual Positions ===")
        
        timestamp = str(int(time.time() * 1000))
        params = {
            'timestamp': timestamp
        }
        
        query_string = urlencode(params)
        signature = self._sign(query_string)
        params['signature'] = signature
        
        headers = {
            'X-BX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        
        url = f"{self.base_url}/openApi/swap/v2/user/positions"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as response:
                    print(f"Status: {response.status}")
                    text = await response.text()
                    print(f"Response: {text}")
                    
                    if response.status == 200:
                        data = json.loads(text)
                        if data.get('code') == 0:
                            print("[OK] Perpetual positions retrieved successfully!")
                            positions = data.get('data', [])
                            if positions:
                                for pos in positions[:3]:  # Show first 3 positions
                                    print(f"  {pos.get('symbol', 'N/A')}: Size {pos.get('positionAmt', 0)}")
                            else:
                                print("  No open positions")
                        else:
                            print(f"[ERROR] API Error: {data.get('msg', 'Unknown error')}")
                    else:
                        print(f"[ERROR] HTTP {response.status}: {text}")
        except Exception as e:
            print(f"[ERROR] Connection failed: {str(e)}")


async def main():
    """Run BingX tests"""
    
    # API credentials
    api_key = "0C28Z4AmyfcoRkw9f90LBmdCuLu4MPnCVezmWDRJRXMYOsp3YLvBsQqKZuxcWHJZlhAcPTuRAv8aj37LVA"
    secret_key = "pwtKT190qBL7h7380QwdftT0OpkL71lc0NZExppsOAo2Ss07je4Q9zCP3RdYFycsr0PudK6TClVIKqXfkSQ"
    
    print("BingX API Connection Test")
    print("=" * 40)
    
    tester = BingXTester(api_key, secret_key)
    
    await tester.test_symbols()
    await tester.test_account_info()
    await tester.test_perpetual_positions()
    
    print("\n" + "=" * 40)
    print("BingX test completed!")


if __name__ == "__main__":
    asyncio.run(main())