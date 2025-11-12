#!/usr/bin/env python3
"""
Script to fetch all supported tokens on OKX Perpetual and Hyperliquid Perpetual
and find the intersection (tokens available on both exchanges)
"""

import json
import urllib.request
import urllib.parse
from typing import Set, Dict, List


def get_okx_perpetual_tokens() -> Set[str]:
    """Fetch all perpetual tokens from OKX"""
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read())
                tokens = set()
                for instrument in data.get('data', []):
                    inst_id = instrument.get('instId', '')
                    # Extract base currency from instrument ID
                    # Format: BTC-USDT-SWAP -> BTC
                    if '-USDT-SWAP' in inst_id:
                        token = inst_id.split('-')[0]
                        tokens.add(token)
                return tokens
            else:
                print(f"OKX API error: {response.status}")
                return set()
    except Exception as e:
        print(f"Error fetching OKX tokens: {e}")
        return set()


def get_hyperliquid_tokens() -> Set[str]:
    """Fetch all perpetual tokens from Hyperliquid"""
    url = "https://api.hyperliquid.xyz/info"
    payload = json.dumps({"type": "meta"}).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read())
                tokens = set()
                for asset in data.get('universe', []):
                    token = asset.get('name', '').split('-')[0]
                    if token:
                        tokens.add(token)
                return tokens
            else:
                print(f"Hyperliquid API error: {response.status}")
                return set()
    except Exception as e:
        print(f"Error fetching Hyperliquid tokens: {e}")
        return set()


def main():
    """Main function"""
    print("=" * 80)
    print("FETCHING SUPPORTED TOKENS")
    print("=" * 80)

    # Fetch tokens from both exchanges
    print("\nFetching tokens from OKX Perpetual...")
    okx_tokens = get_okx_perpetual_tokens()
    print(f"✓ OKX Perpetual: {len(okx_tokens)} tokens")

    print("\nFetching tokens from Hyperliquid...")
    hyperliquid_tokens = get_hyperliquid_tokens()
    print(f"✓ Hyperliquid: {len(hyperliquid_tokens)} tokens")

    # Find intersection
    common_tokens = okx_tokens & hyperliquid_tokens

    print("\n" + "=" * 80)
    print(f"COMMON TOKENS (Available on both exchanges): {len(common_tokens)}")
    print("=" * 80)

    # Sort tokens by popularity (common major tokens first)
    major_tokens = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'MATIC', 'DOT', 'AVAX']

    sorted_common = []
    for token in major_tokens:
        if token in common_tokens:
            sorted_common.append(token)
            common_tokens.remove(token)

    # Add remaining tokens in alphabetical order
    sorted_common.extend(sorted(common_tokens))

    # Print in columns
    print("\nMajor tokens (high liquidity, recommended):")
    major_found = [t for t in major_tokens if t in sorted_common]
    for i in range(0, len(major_found), 5):
        print("  " + ", ".join(f"{t:6}" for t in major_found[i:i+5]))

    print("\nAll other tokens (alphabetical):")
    other_tokens = [t for t in sorted_common if t not in major_found]
    for i in range(0, len(other_tokens), 8):
        print("  " + ", ".join(f"{t:6}" for t in other_tokens[i:i+8]))

    # Generate YAML config
    print("\n" + "=" * 80)
    print("YAML CONFIGURATION FOR conf/funding_rate_arb.yml")
    print("=" * 80)

    yaml_tokens = "\n".join(f"  - {token}" for token in sorted_common)

    print(f"""
tokens:
{yaml_tokens}
""")

    # Also print only major tokens option
    print("\n" + "=" * 80)
    print("RECOMMENDED: Major tokens only (high liquidity)")
    print("=" * 80)

    yaml_major = "\n".join(f"  - {token}" for token in major_found)

    print(f"""
tokens:
{yaml_major}
""")

    # Save to file
    output = {
        "okx_tokens": sorted(list(okx_tokens)),
        "hyperliquid_tokens": sorted(list(hyperliquid_tokens)),
        "common_tokens": sorted_common,
        "major_tokens": major_found,
        "other_tokens": other_tokens
    }

    with open('supported_tokens.json', 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved detailed list to: supported_tokens.json")

    # Show tokens only on one exchange
    okx_only = okx_tokens - hyperliquid_tokens
    hyperliquid_only = hyperliquid_tokens - okx_tokens

    print("\n" + "=" * 80)
    print("EXCHANGE-SPECIFIC TOKENS")
    print("=" * 80)
    print(f"\nOnly on OKX ({len(okx_only)} tokens):")
    if okx_only:
        okx_only_list = sorted(list(okx_only))
        for i in range(0, len(okx_only_list), 8):
            print("  " + ", ".join(f"{t:6}" for t in okx_only_list[i:i+8]))

    print(f"\nOnly on Hyperliquid ({len(hyperliquid_only)} tokens):")
    if hyperliquid_only:
        hyperliquid_only_list = sorted(list(hyperliquid_only))
        for i in range(0, len(hyperliquid_only_list), 8):
            print("  " + ", ".join(f"{t:6}" for t in hyperliquid_only_list[i:i+8]))

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
