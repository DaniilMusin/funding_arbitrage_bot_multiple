#!/usr/bin/env python3
"""
Public-API e2e paper run for funding arbitrage logic.

This runner does NOT require exchange API keys.
It uses public endpoints (funding + mark price) and simulates position open/close.
"""

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import aiohttp
except Exception as exc:
    raise SystemExit(f"aiohttp is required: {exc}")

try:
    import yaml
except Exception as exc:
    raise SystemExit(f"pyyaml is required: {exc}")


DAY_SECONDS = Decimal("86400")
FUNDING_INTERVAL_SECONDS = {
    "okx_perpetual": Decimal("28800"),         # 8h
    "bybit_perpetual": Decimal("28800"),       # 8h
    "hyperliquid_perpetual": Decimal("3600"),  # 1h
}
SUPPORTED_CONNECTORS = set(FUNDING_INTERVAL_SECONDS.keys())
DEFAULT_TAKER_FEE_BPS = {
    "okx_perpetual": Decimal("5.0"),
    "bybit_perpetual": Decimal("5.5"),
    "hyperliquid_perpetual": Decimal("2.5"),
}
DEFAULT_HALF_SPREAD_BPS = {
    "okx_perpetual": Decimal("1.0"),
    "bybit_perpetual": Decimal("1.0"),
    "hyperliquid_perpetual": Decimal("1.5"),
}
DEFAULT_MARKET_IMPACT_BPS = {
    "okx_perpetual": Decimal("1.5"),
    "bybit_perpetual": Decimal("1.5"),
    "hyperliquid_perpetual": Decimal("2.0"),
}


@dataclass
class FundingSnapshot:
    connector: str
    token: str
    funding_rate: Decimal
    mark_price: Decimal
    next_funding_ts: Optional[float]
    fetched_ts: float

    @property
    def funding_rate_per_second(self) -> Decimal:
        interval = FUNDING_INTERVAL_SECONDS[self.connector]
        return self.funding_rate / interval


@dataclass
class SimPosition:
    token: str
    long_connector: str
    short_connector: str
    size_quote: Decimal
    opened_ts: float
    long_entry_price: Decimal
    short_entry_price: Decimal
    long_open_fee_quote: Decimal = Decimal("0")
    short_open_fee_quote: Decimal = Decimal("0")
    funding_pnl: Decimal = Decimal("0")
    last_update_ts: float = 0.0


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_connector_bps_map(raw: Any) -> Dict[str, Decimal]:
    result: Dict[str, Decimal] = {}
    if not isinstance(raw, dict):
        return result
    for key, value in raw.items():
        connector = str(key).strip()
        if connector not in SUPPORTED_CONNECTORS:
            continue
        bps = to_decimal(value, Decimal("0"))
        if bps < 0:
            continue
        result[connector] = bps
    return result


def build_rate_map(
    connectors: Sequence[str],
    default_bps: Dict[str, Decimal],
    per_connector_bps: Optional[Dict[str, Decimal]] = None,
    global_bps: Optional[Decimal] = None,
) -> Dict[str, Decimal]:
    rates: Dict[str, Decimal] = {}
    for connector in connectors:
        bps = default_bps.get(connector, Decimal("0"))
        if per_connector_bps and connector in per_connector_bps:
            bps = per_connector_bps[connector]
        if global_bps is not None and global_bps >= 0:
            bps = global_bps
        bps = max(Decimal("0"), bps)
        rates[connector] = bps / Decimal("10000")
    return rates
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def load_yaml(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


async def fetch_okx_snapshot(session: aiohttp.ClientSession, token: str) -> Optional[FundingSnapshot]:
    inst_id = f"{token}-USDT-SWAP"
    funding_url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
    ticker_url = f"https://www.okx.com/api/v5/market/ticker?instId={inst_id}"
    now = time.time()
    try:
        async with session.get(funding_url) as response:
            if response.status != 200:
                return None
            payload = await response.json()
        data = (payload.get("data") or [{}])[0]
        funding_rate = to_decimal(data.get("fundingRate"))
        next_funding_ms = data.get("nextFundingTime")
        next_funding_ts = (float(next_funding_ms) / 1000.0) if next_funding_ms else None
        mark_price = to_decimal(data.get("markPx"))

        if mark_price <= 0:
            async with session.get(ticker_url) as response:
                if response.status != 200:
                    return None
                ticker_payload = await response.json()
            ticker_data = (ticker_payload.get("data") or [{}])[0]
            mark_price = to_decimal(ticker_data.get("last"))

        if mark_price <= 0:
            return None
        return FundingSnapshot(
            connector="okx_perpetual",
            token=token,
            funding_rate=funding_rate,
            mark_price=mark_price,
            next_funding_ts=next_funding_ts,
            fetched_ts=now,
        )
    except Exception:
        return None


async def fetch_bybit_snapshot(session: aiohttp.ClientSession, token: str) -> Optional[FundingSnapshot]:
    symbol = f"{token}USDT"
    url = f"https://api.bybit.com/v5/market/tickers?category=linear&symbol={symbol}"
    now = time.time()
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return None
            payload = await response.json()
        if payload.get("retCode") != 0:
            return None
        data = (payload.get("result", {}).get("list") or [{}])[0]
        funding_rate = to_decimal(data.get("fundingRate"))
        mark_price = to_decimal(data.get("markPrice"))
        next_funding_ms = data.get("nextFundingTime")
        next_funding_ts = (float(next_funding_ms) / 1000.0) if next_funding_ms else None
        if mark_price <= 0:
            return None
        return FundingSnapshot(
            connector="bybit_perpetual",
            token=token,
            funding_rate=funding_rate,
            mark_price=mark_price,
            next_funding_ts=next_funding_ts,
            fetched_ts=now,
        )
    except Exception:
        return None


async def fetch_hyperliquid_snapshots(
    session: aiohttp.ClientSession,
    tokens: Sequence[str],
) -> Dict[str, FundingSnapshot]:
    now = time.time()
    snapshots: Dict[str, FundingSnapshot] = {}
    try:
        async with session.post("https://api.hyperliquid.xyz/info", json={"type": "metaAndAssetCtxs"}) as response:
            if response.status != 200:
                return snapshots
            payload = await response.json()

        if not isinstance(payload, list) or len(payload) < 2:
            return snapshots
        meta = payload[0] or {}
        contexts = payload[1] or []
        universe = meta.get("universe") or []
        if not isinstance(universe, list) or not isinstance(contexts, list):
            return snapshots

        for index, item in enumerate(universe):
            if index >= len(contexts):
                continue
            token = str(item.get("name", "")).upper()
            if token not in tokens:
                continue
            ctx = contexts[index] or {}
            funding_rate = to_decimal(ctx.get("funding"))
            mark_price = to_decimal(ctx.get("markPx"))
            if mark_price <= 0:
                continue
            snapshots[token] = FundingSnapshot(
                connector="hyperliquid_perpetual",
                token=token,
                funding_rate=funding_rate,
                mark_price=mark_price,
                next_funding_ts=None,
                fetched_ts=now,
            )
    except Exception:
        return snapshots
    return snapshots


def pick_best_opportunity(
    token: str,
    token_snapshots: Dict[str, FundingSnapshot],
    min_profitability_daily: Decimal,
    allowed_connectors: Optional[Sequence[str]] = None,
) -> Optional[Tuple[str, str, Decimal]]:
    best: Optional[Tuple[str, str, Decimal]] = None
    if allowed_connectors is None:
        connectors = list(token_snapshots.keys())
    else:
        allowed = set(allowed_connectors)
        connectors = [connector for connector in token_snapshots.keys() if connector in allowed]
    for i, c1 in enumerate(connectors):
        for c2 in connectors[i + 1:]:
            s1 = token_snapshots[c1]
            s2 = token_snapshots[c2]
            diff_per_second = s2.funding_rate_per_second - s1.funding_rate_per_second
            daily_diff = diff_per_second * DAY_SECONDS
            if daily_diff > 0:
                long_connector = c1
                short_connector = c2
                score = daily_diff
            else:
                long_connector = c2
                short_connector = c1
                score = -daily_diff
            if score < min_profitability_daily:
                continue
            if best is None or score > best[2]:
                best = (long_connector, short_connector, score)
    return best


def update_position_metrics(
    position: SimPosition,
    long_snapshot: FundingSnapshot,
    short_snapshot: FundingSnapshot,
    now: float,
    execution_cost_rate_by_connector: Dict[str, Decimal],
    taker_fee_rate_by_connector: Dict[str, Decimal],
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    if position.last_update_ts <= 0:
        position.last_update_ts = now
    elapsed = max(0.0, now - position.last_update_ts)
    elapsed_dec = Decimal(str(elapsed))

    # Funding: short receives positive rate, long pays positive rate.
    funding_delta = position.size_quote * elapsed_dec * (
        short_snapshot.funding_rate_per_second - long_snapshot.funding_rate_per_second
    )
    position.funding_pnl += funding_delta
    position.last_update_ts = now

    long_execution_cost = execution_cost_rate_by_connector.get(position.long_connector, Decimal("0"))
    short_execution_cost = execution_cost_rate_by_connector.get(position.short_connector, Decimal("0"))

    # Exit at executable prices (not mid): long sells worse than mark, short buys back worse than mark.
    long_exit_price = long_snapshot.mark_price * (Decimal("1") - long_execution_cost)
    short_exit_price = short_snapshot.mark_price * (Decimal("1") + short_execution_cost)
    if long_exit_price <= 0 or short_exit_price <= 0:
        return Decimal("0"), position.funding_pnl, Decimal("0"), position.funding_pnl

    long_trade_pnl = position.size_quote * ((long_exit_price / position.long_entry_price) - Decimal("1"))
    short_trade_pnl = position.size_quote * ((position.short_entry_price / short_exit_price) - Decimal("1"))
    trade_pnl = long_trade_pnl + short_trade_pnl

    long_close_fee = position.size_quote * taker_fee_rate_by_connector.get(position.long_connector, Decimal("0"))
    short_close_fee = position.size_quote * taker_fee_rate_by_connector.get(position.short_connector, Decimal("0"))
    fees_total = position.long_open_fee_quote + position.short_open_fee_quote + long_close_fee + short_close_fee

    total_pnl = trade_pnl + position.funding_pnl - fees_total
    return trade_pnl, position.funding_pnl, fees_total, total_pnl


def get_connector_position_counts(
    active_positions: Dict[str, SimPosition],
    connectors: Sequence[str],
) -> Dict[str, int]:
    counts = {connector: 0 for connector in connectors}
    for position in active_positions.values():
        counts[position.long_connector] = counts.get(position.long_connector, 0) + 1
        counts[position.short_connector] = counts.get(position.short_connector, 0) + 1
    return counts


async def run_public_e2e(
    connectors: Sequence[str],
    tokens: Sequence[str],
    min_profitability_daily: Decimal,
    take_profit_ratio: Decimal,
    funding_stop_loss_daily: Decimal,
    position_size_quote: Decimal,
    max_positions_per_connector: int,
    take_any_profit_when_funding_positive: bool,
    execution_cost_rate_by_connector: Dict[str, Decimal],
    taker_fee_rate_by_connector: Dict[str, Decimal],
    duration_seconds: int,
    poll_interval_seconds: int,
    request_timeout_seconds: int,
) -> Dict[str, Any]:
    active_positions: Dict[str, SimPosition] = {}
    closed_positions: List[Dict[str, Any]] = []
    loop_errors = 0
    last_snapshots_by_token: Dict[str, Dict[str, FundingSnapshot]] = {}

    timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        started = time.time()
        next_log_ts = started
        while True:
            now = time.time()
            if now - started >= duration_seconds:
                break

            snapshots_by_token: Dict[str, Dict[str, FundingSnapshot]] = {token: {} for token in tokens}

            fetch_tasks = []
            for token in tokens:
                if "okx_perpetual" in connectors:
                    fetch_tasks.append(("okx_perpetual", token, fetch_okx_snapshot(session, token)))
                if "bybit_perpetual" in connectors:
                    fetch_tasks.append(("bybit_perpetual", token, fetch_bybit_snapshot(session, token)))

            if fetch_tasks:
                results = await asyncio.gather(*(task for _, _, task in fetch_tasks), return_exceptions=True)
                for (connector_name, token, _), result in zip(fetch_tasks, results):
                    if isinstance(result, FundingSnapshot):
                        snapshots_by_token[token][connector_name] = result

            if "hyperliquid_perpetual" in connectors:
                hl_snapshots = await fetch_hyperliquid_snapshots(session, tokens)
                for token, snapshot in hl_snapshots.items():
                    snapshots_by_token[token]["hyperliquid_perpetual"] = snapshot
            last_snapshots_by_token = snapshots_by_token

            ranked_candidates: List[Tuple[str, Decimal]] = []
            for token in tokens:
                if token in active_positions:
                    continue
                token_snapshots = snapshots_by_token[token]
                if len(token_snapshots) < 2:
                    continue
                best_any = pick_best_opportunity(
                    token=token,
                    token_snapshots=token_snapshots,
                    min_profitability_daily=min_profitability_daily,
                )
                if best_any is None:
                    continue
                ranked_candidates.append((token, best_any[2]))
            ranked_candidates.sort(key=lambda item: item[1], reverse=True)

            for token, _ in ranked_candidates:
                token_snapshots = snapshots_by_token[token]
                if len(token_snapshots) < 2:
                    continue

                allowed_connectors: Optional[Sequence[str]] = None
                if max_positions_per_connector > 0:
                    connector_counts = get_connector_position_counts(active_positions, connectors)
                    allowed_connectors = [
                        connector_name
                        for connector_name, count in connector_counts.items()
                        if count < max_positions_per_connector
                    ]
                    if len(allowed_connectors) < 2:
                        break

                best = pick_best_opportunity(
                    token=token,
                    token_snapshots=token_snapshots,
                    min_profitability_daily=min_profitability_daily,
                    allowed_connectors=allowed_connectors,
                )
                if best is None:
                    continue
                long_connector, short_connector, expected_daily = best
                long_snapshot = token_snapshots[long_connector]
                short_snapshot = token_snapshots[short_connector]

                long_execution_cost = execution_cost_rate_by_connector.get(long_connector, Decimal("0"))
                short_execution_cost = execution_cost_rate_by_connector.get(short_connector, Decimal("0"))
                long_entry_price = long_snapshot.mark_price * (Decimal("1") + long_execution_cost)
                short_entry_price = short_snapshot.mark_price * (Decimal("1") - short_execution_cost)
                if long_entry_price <= 0 or short_entry_price <= 0:
                    continue

                long_open_fee_quote = position_size_quote * taker_fee_rate_by_connector.get(long_connector, Decimal("0"))
                short_open_fee_quote = position_size_quote * taker_fee_rate_by_connector.get(short_connector, Decimal("0"))
                active_positions[token] = SimPosition(
                    token=token,
                    long_connector=long_connector,
                    short_connector=short_connector,
                    size_quote=position_size_quote,
                    opened_ts=now,
                    long_entry_price=long_entry_price,
                    short_entry_price=short_entry_price,
                    long_open_fee_quote=long_open_fee_quote,
                    short_open_fee_quote=short_open_fee_quote,
                    last_update_ts=now,
                )
                print(
                    f"[OPEN] {token}: long={long_connector} short={short_connector} "
                    f"expected_daily={expected_daily:.6%} size={position_size_quote} "
                    f"entry_exec_cost={long_execution_cost + short_execution_cost:.4%} "
                    f"open_fees={long_open_fee_quote + short_open_fee_quote:.6f}"
                )

            for token, active in list(active_positions.items()):
                token_snapshots = snapshots_by_token.get(token, {})
                long_snapshot = token_snapshots.get(active.long_connector)
                short_snapshot = token_snapshots.get(active.short_connector)
                if long_snapshot is None or short_snapshot is None:
                    continue

                trade_pnl, funding_pnl, fees_total, total_pnl = update_position_metrics(
                    active,
                    long_snapshot,
                    short_snapshot,
                    now,
                    execution_cost_rate_by_connector=execution_cost_rate_by_connector,
                    taker_fee_rate_by_connector=taker_fee_rate_by_connector,
                )
                pnl_ratio = total_pnl / active.size_quote if active.size_quote > 0 else Decimal("0")

                funding_daily = (
                    (short_snapshot.funding_rate_per_second - long_snapshot.funding_rate_per_second) * DAY_SECONDS
                )
                should_close_tp = pnl_ratio >= take_profit_ratio
                should_close_stop = funding_daily < funding_stop_loss_daily
                should_close_any_profit = (
                    take_any_profit_when_funding_positive
                    and total_pnl > 0
                    and funding_daily > 0
                )
                if should_close_stop or should_close_any_profit or should_close_tp:
                    if should_close_stop:
                        reason = "funding_stop_loss"
                    elif should_close_any_profit:
                        reason = "take_any_profit"
                    else:
                        reason = "take_profit"
                    closed_positions.append(
                        {
                            "token": token,
                            "reason": reason,
                            "opened_ts": active.opened_ts,
                            "closed_ts": now,
                            "long_connector": active.long_connector,
                            "short_connector": active.short_connector,
                            "trade_pnl": str(trade_pnl),
                            "funding_pnl": str(funding_pnl),
                            "fees_total": str(fees_total),
                            "total_pnl": str(total_pnl),
                            "pnl_ratio": str(pnl_ratio),
                            "funding_daily": str(funding_daily),
                        }
                    )
                    print(
                        f"[CLOSE] {token}: reason={reason} total_pnl={total_pnl:.6f} "
                        f"pnl_ratio={pnl_ratio:.4%} funding_daily={funding_daily:.6%} "
                        f"fees_total={fees_total:.6f}"
                    )
                    del active_positions[token]

            if now >= next_log_ts:
                next_log_ts = now + max(10, poll_interval_seconds * 3)
                connector_counts = get_connector_position_counts(active_positions, connectors)
                counts_repr = ",".join(f"{name}:{count}" for name, count in connector_counts.items())
                print(
                    f"[HEARTBEAT] active={len(active_positions)} closed={len(closed_positions)} "
                    f"tokens={len(tokens)} connectors={len(connectors)} connector_counts={counts_repr}"
                )

            try:
                await asyncio.sleep(poll_interval_seconds)
            except Exception:
                loop_errors += 1

        total_closed_pnl = sum(Decimal(item["total_pnl"]) for item in closed_positions)
        total_open_pnl = Decimal("0")
        now = time.time()
        active_positions_report: List[Dict[str, Any]] = []
        open_pnl_unavailable_count = 0

        # Final refresh for active tokens to improve end-of-run open PnL accuracy.
        final_snapshots_by_token: Dict[str, Dict[str, FundingSnapshot]] = {token: {} for token in active_positions.keys()}
        active_tokens = list(active_positions.keys())
        if active_tokens:
            fetch_tasks = []
            for token in active_tokens:
                if "okx_perpetual" in connectors:
                    fetch_tasks.append(("okx_perpetual", token, fetch_okx_snapshot(session, token)))
                if "bybit_perpetual" in connectors:
                    fetch_tasks.append(("bybit_perpetual", token, fetch_bybit_snapshot(session, token)))
            if fetch_tasks:
                results = await asyncio.gather(*(task for _, _, task in fetch_tasks), return_exceptions=True)
                for (connector_name, token, _), result in zip(fetch_tasks, results):
                    if isinstance(result, FundingSnapshot):
                        final_snapshots_by_token[token][connector_name] = result
            if "hyperliquid_perpetual" in connectors:
                hl_snapshots = await fetch_hyperliquid_snapshots(session, active_tokens)
                for token, snapshot in hl_snapshots.items():
                    final_snapshots_by_token[token]["hyperliquid_perpetual"] = snapshot

        for token, position in active_positions.items():
            token_snapshots = final_snapshots_by_token.get(token) or last_snapshots_by_token.get(token, {})
            long_snapshot = token_snapshots.get(position.long_connector)
            short_snapshot = token_snapshots.get(position.short_connector)
            if long_snapshot is None or short_snapshot is None:
                open_pnl_unavailable_count += 1
                active_positions_report.append(
                    {
                        "token": token,
                        "long_connector": position.long_connector,
                        "short_connector": position.short_connector,
                        "opened_ts": position.opened_ts,
                        "pnl_unavailable": True,
                    }
                )
                continue

            trade_pnl, funding_pnl, fees_total, total_pnl = update_position_metrics(
                position,
                long_snapshot,
                short_snapshot,
                now,
                execution_cost_rate_by_connector=execution_cost_rate_by_connector,
                taker_fee_rate_by_connector=taker_fee_rate_by_connector,
            )
            pnl_ratio = total_pnl / position.size_quote if position.size_quote > 0 else Decimal("0")
            funding_daily = (
                (short_snapshot.funding_rate_per_second - long_snapshot.funding_rate_per_second) * DAY_SECONDS
            )
            total_open_pnl += total_pnl
            active_positions_report.append(
                {
                    "token": token,
                    "long_connector": position.long_connector,
                    "short_connector": position.short_connector,
                    "opened_ts": position.opened_ts,
                    "trade_pnl": str(trade_pnl),
                    "funding_pnl": str(funding_pnl),
                    "fees_total": str(fees_total),
                    "total_pnl": str(total_pnl),
                    "pnl_ratio": str(pnl_ratio),
                    "funding_daily": str(funding_daily),
                    "pnl_unavailable": False,
                }
            )

    return {
        "duration_seconds": duration_seconds,
        "connectors": list(connectors),
        "tokens": list(tokens),
        "max_positions_per_connector": max_positions_per_connector,
        "take_any_profit_when_funding_positive": take_any_profit_when_funding_positive,
        "execution_cost_bps_by_connector": {
            connector: str((execution_cost_rate_by_connector.get(connector, Decimal("0")) * Decimal("10000")))
            for connector in connectors
        },
        "taker_fee_bps_by_connector": {
            connector: str((taker_fee_rate_by_connector.get(connector, Decimal("0")) * Decimal("10000")))
            for connector in connectors
        },
        "active_positions": active_positions_report,
        "closed_positions": closed_positions,
        "active_positions_count": len(active_positions),
        "closed_positions_count": len(closed_positions),
        "closed_total_pnl_quote": str(total_closed_pnl),
        "open_total_pnl_quote": str(total_open_pnl),
        "total_pnl_quote": str(total_closed_pnl + total_open_pnl),
        "open_pnl_unavailable_count": open_pnl_unavailable_count,
        "loop_errors": loop_errors,
        "finished_ts": now,
    }


def parse_csv_list(value: str) -> List[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run keyless public-API funding arbitrage e2e paper simulation."
    )
    parser.add_argument("--config", default="conf/scripts/v2_funding_rate_arb.yml")
    parser.add_argument("--connectors", default="")
    parser.add_argument("--tokens", default="")
    parser.add_argument("--max-tokens", type=int, default=3)
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--request-timeout-seconds", type=int, default=10)
    parser.add_argument("--min-profitability-daily", default="")
    parser.add_argument("--take-profit-ratio", default="")
    parser.add_argument("--funding-stop-loss-daily", default="")
    parser.add_argument("--position-size-quote", default="")
    parser.add_argument("--max-positions-per-connector", default="")
    parser.add_argument("--taker-fee-bps", default="")
    parser.add_argument("--half-spread-bps", default="")
    parser.add_argument("--market-impact-bps", default="")
    parser.add_argument("--take-any-profit-when-funding-positive", default="")
    parser.add_argument("--output-json", default="")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Windows: aiodns/aiohttp requires SelectorEventLoop.
    if os.name == "nt" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    cfg = load_yaml(args.config)
    cfg_connectors = cfg.get("connectors") or []
    cfg_tokens = cfg.get("tokens") or []

    connectors = parse_csv_list(args.connectors) if args.connectors else [str(c) for c in cfg_connectors]
    tokens = parse_csv_list(args.tokens) if args.tokens else [str(t).upper() for t in cfg_tokens]

    connectors = [c for c in connectors if c in SUPPORTED_CONNECTORS]
    if len(connectors) < 2:
        print("Need at least 2 supported connectors from: okx_perpetual, bybit_perpetual, hyperliquid_perpetual")
        return 2

    if not tokens:
        print("No tokens provided in args or config.")
        return 2
    tokens = tokens[: max(1, args.max_tokens)]

    min_profitability_daily = to_decimal(
        args.min_profitability_daily if args.min_profitability_daily else cfg.get("min_funding_rate_profitability"),
        Decimal("0.001"),
    )
    take_profit_ratio = to_decimal(
        args.take_profit_ratio if args.take_profit_ratio else cfg.get("profitability_to_take_profit"),
        Decimal("0.01"),
    )
    funding_stop_loss_daily = to_decimal(
        args.funding_stop_loss_daily if args.funding_stop_loss_daily else cfg.get("funding_rate_diff_stop_loss"),
        Decimal("-0.001"),
    )
    position_size_quote = to_decimal(
        args.position_size_quote if args.position_size_quote else cfg.get("position_size_quote"),
        Decimal("100"),
    )
    if position_size_quote <= 0:
        position_size_quote = Decimal("100")
    max_positions_per_connector = 0
    raw_max_positions = (
        args.max_positions_per_connector
        if args.max_positions_per_connector
        else cfg.get("max_positions_per_connector", 0)
    )
    try:
        max_positions_per_connector = int(raw_max_positions)
    except (TypeError, ValueError):
        max_positions_per_connector = 0
    if max_positions_per_connector < 0:
        max_positions_per_connector = 0

    cfg_take_any_profit = to_bool(cfg.get("take_any_profit_when_funding_positive"), True)
    take_any_profit_when_funding_positive = (
        to_bool(args.take_any_profit_when_funding_positive, cfg_take_any_profit)
        if args.take_any_profit_when_funding_positive
        else cfg_take_any_profit
    )

    cfg_taker_fee_bps_map = parse_connector_bps_map(cfg.get("paper_taker_fee_bps_by_connector"))
    cfg_half_spread_bps_map = parse_connector_bps_map(cfg.get("paper_half_spread_bps_by_connector"))
    cfg_market_impact_bps_map = parse_connector_bps_map(cfg.get("paper_market_impact_bps_by_connector"))

    cfg_taker_fee_bps_global = to_decimal(cfg.get("paper_taker_fee_bps"), Decimal("-1"))
    cfg_half_spread_bps_global = to_decimal(cfg.get("paper_half_spread_bps"), Decimal("-1"))
    cfg_market_impact_bps_global = to_decimal(cfg.get("paper_market_impact_bps"), Decimal("-1"))

    taker_fee_bps_global = (
        to_decimal(args.taker_fee_bps, Decimal("-1"))
        if args.taker_fee_bps
        else cfg_taker_fee_bps_global
    )
    half_spread_bps_global = (
        to_decimal(args.half_spread_bps, Decimal("-1"))
        if args.half_spread_bps
        else cfg_half_spread_bps_global
    )
    market_impact_bps_global = (
        to_decimal(args.market_impact_bps, Decimal("-1"))
        if args.market_impact_bps
        else cfg_market_impact_bps_global
    )

    taker_fee_rate_by_connector = build_rate_map(
        connectors=connectors,
        default_bps=DEFAULT_TAKER_FEE_BPS,
        per_connector_bps=cfg_taker_fee_bps_map,
        global_bps=taker_fee_bps_global,
    )
    half_spread_rate_by_connector = build_rate_map(
        connectors=connectors,
        default_bps=DEFAULT_HALF_SPREAD_BPS,
        per_connector_bps=cfg_half_spread_bps_map,
        global_bps=half_spread_bps_global,
    )
    market_impact_rate_by_connector = build_rate_map(
        connectors=connectors,
        default_bps=DEFAULT_MARKET_IMPACT_BPS,
        per_connector_bps=cfg_market_impact_bps_map,
        global_bps=market_impact_bps_global,
    )
    execution_cost_rate_by_connector = {
        connector: half_spread_rate_by_connector.get(connector, Decimal("0"))
        + market_impact_rate_by_connector.get(connector, Decimal("0"))
        for connector in connectors
    }

    print("=" * 80)
    print("Funding Arbitrage Public e2e (Keyless Paper)")
    print("=" * 80)
    print(f"Config file: {args.config}")
    print(f"Connectors: {', '.join(connectors)}")
    print(f"Tokens: {', '.join(tokens)}")
    print(f"Duration: {args.duration_seconds}s | Poll interval: {args.poll_interval_seconds}s")
    print(f"Min funding profitability (daily): {min_profitability_daily:.6%}")
    print(f"Take-profit ratio: {take_profit_ratio:.4%}")
    print(f"Funding stop-loss (daily): {funding_stop_loss_daily:.6%}")
    print(f"Position size quote: {position_size_quote}")
    print(f"Max positions per connector: {max_positions_per_connector}")
    print(f"Take any profit when funding positive: {take_any_profit_when_funding_positive}")
    execution_cost_bps_display = ", ".join(
        f"{c}:{(execution_cost_rate_by_connector.get(c, Decimal('0')) * Decimal('10000')):.2f}"
        for c in connectors
    )
    taker_fee_bps_display = ", ".join(
        f"{c}:{(taker_fee_rate_by_connector.get(c, Decimal('0')) * Decimal('10000')):.2f}"
        for c in connectors
    )
    print(f"Execution cost (spread+impact, bps): {execution_cost_bps_display}")
    print(f"Taker fee (bps): {taker_fee_bps_display}")
    print("=" * 80)

    report = asyncio.run(
        run_public_e2e(
            connectors=connectors,
            tokens=tokens,
            min_profitability_daily=min_profitability_daily,
            take_profit_ratio=take_profit_ratio,
            funding_stop_loss_daily=funding_stop_loss_daily,
            position_size_quote=position_size_quote,
            max_positions_per_connector=max_positions_per_connector,
            take_any_profit_when_funding_positive=take_any_profit_when_funding_positive,
            execution_cost_rate_by_connector=execution_cost_rate_by_connector,
            taker_fee_rate_by_connector=taker_fee_rate_by_connector,
            duration_seconds=max(10, args.duration_seconds),
            poll_interval_seconds=max(1, args.poll_interval_seconds),
            request_timeout_seconds=max(3, args.request_timeout_seconds),
        )
    )

    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Closed positions: {report['closed_positions_count']}")
    print(f"Active positions: {report['active_positions_count']}")
    print(f"Closed total PnL (quote): {report['closed_total_pnl_quote']}")
    print(f"Open total PnL (quote): {report['open_total_pnl_quote']}")
    print(f"Total PnL (quote): {report['total_pnl_quote']}")
    print(f"Open PnL unavailable count: {report['open_pnl_unavailable_count']}")
    print(f"Loop errors: {report['loop_errors']}")

    output_json = args.output_json
    if not output_json:
        ts = int(time.time())
        output_json = os.path.join("logs", f"funding_public_e2e_{ts}.json")
    out_path = Path(output_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Report saved to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
