# Deep Audit: Arbitrage Logic, Order Validation, Critical Scenarios

## Date: 2025-01-15

Comprehensive analysis of arbitrage pair selection, order execution validation, and critical scenario handling.

---

## 🎯 Audit Scope

1. ✅ Trading pair selection logic (same tokens across exchanges)
2. ✅ Order execution validation (both positions opened successfully)
3. ✅ Critical scenario handling (partial fills, failures, network issues)

---

## 🔍 CRITICAL ISSUES FOUND

### 🚨 CRITICAL #1: Race Condition - Position Added Before Validation

**Location**: `scripts/v2_funding_rate_arb.py:744-763`

**Severity**: CRITICAL - Can cause unhedged positions!

#### Problem:

```python
# Line 744: Position added to active_funding_arbitrages IMMEDIATELY
self.active_funding_arbitrages[token] = {
    "connector_1": connector_1,
    "connector_2": connector_2,
    "executors_ids": [position_executor_config_1.id, position_executor_config_2.id],
    "side": trade_side,
    "funding_payments": [],
    "position_size_quote": position_size_quote,
}

# Line 762: CreateExecutorAction sent (orders NOT executed yet!)
create_actions.extend([CreateExecutorAction(executor_config=position_executor_config_1),
                      CreateExecutorAction(executor_config=position_executor_config_2)])
```

**Timeline of Events:**

1. **T=0s**: Position added to `active_funding_arbitrages`
2. **T=0s**: `CreateExecutorAction` created (orders sent to exchange)
3. **T=0.1s - 1s**: Orders execute on exchanges (maybe partial fill, maybe fail)
4. **T=1s+**: Next tick - `stop_actions_proposal()` called
5. **T=1s+**: FIRST TIME `validate_position_hedge()` runs!

**DANGER WINDOW: 1+ seconds of potential unhedged exposure!**

#### Scenarios That Can Go Wrong:

**Scenario A: One order fills, one fails**
- OKX: Order fills 100% (Long BTC $10,000)
- Hyperliquid: Order fails (network error, insufficient liquidity, etc.)
- Bot has UNHEDGED $10,000 long BTC position for 1+ seconds!
- Price moves 1% down = -$100 loss before emergency close triggers

**Scenario B: Partial fills with different percentages**
- OKX: Order fills 100% (Long BTC $10,000)
- Hyperliquid: Order fills 50% (Short BTC $5,000)
- Bot has NET LONG $5,000 BTC position
- Emergency close triggers in next tick, but damage already done

**Scenario C: Both orders pending**
- Both exchanges slow to respond
- Position in `active_funding_arbitrages` but neither order filled
- `validate_position_hedge()` returns False: "position not filled"
- Emergency close triggered, but nothing to close!

#### Impact:

- **Financial Risk**: Unhedged market exposure up to full position size
- **Loss Potential**: Price movement * position_size during danger window
- **Frequency**: Every position opening (high!)

#### Root Cause:

Position added to `active_funding_arbitrages` **synchronously** but orders execute **asynchronously**. No waiting for order confirmation before marking position as active.

---

### ⚠️ HIGH #2: Different Quote Currencies (USDT vs USD)

**Location**: `scripts/v2_funding_rate_arb.py:103-114, 708-709`

**Severity**: HIGH - May cause price discrepancies

#### Problem:

```python
quote_markets_map = {
    "hyperliquid_perpetual": "USD",      # ❌ USD
    "binance_perpetual": "USDT",         # ✅ USDT
    "bybit_perpetual": "USDT",           # ✅ USDT
    "okx_perpetual": "USDT",             # ✅ USDT
    # ...all others use USDT
}
```

**Result for BTC arbitrage:**
- OKX: Trading pair = `BTC-USDT`
- Hyperliquid: Trading pair = `BTC-USD`

#### Is This a Bug?

**Maybe not, but risky:**
- USDT ≈ USD most of the time (peg at $1.00)
- BUT: USDT can depeg (seen in May 2022: USDT = $0.95)
- When depegged: BTC-USDT price ≠ BTC-USD price
- Arbitrage calculation becomes invalid!

#### Example:

**Normal times:**
- BTC-USDT on OKX: $50,000
- BTC-USD on Hyperliquid: $50,000
- ✅ Perfect arbitrage

**USDT depegs to $0.98:**
- BTC-USDT on OKX: $50,000 (but USDT=$0.98, so really $49,000 in USD terms!)
- BTC-USD on Hyperliquid: $50,000
- ❌ FALSE arbitrage signal! Actually losing $1,000!

#### Recommendation:

Either:
1. Use only USDT pairs on all exchanges (exclude Hyperliquid or find USDT pair)
2. Add price adjustment for USDT/USD conversion
3. Monitor USDT peg and pause bot if depeg > 0.5%

---

### ⚠️ MEDIUM #3: No Immediate Post-Execution Validation

**Location**: Entire flow - missing validation step

**Severity**: MEDIUM - Delayed problem detection

#### Current Flow:

```
create_actions_proposal()
  ↓
Add to active_funding_arbitrages  (SYNC)
  ↓
CreateExecutorAction  (ASYNC - orders sent)
  ↓
[NOTHING HAPPENS - WAITING FOR NEXT TICK]
  ↓
stop_actions_proposal() - NEXT TICK
  ↓
validate_position_hedge()  (FIRST VALIDATION!)
```

#### Problem:

- **Delay**: 1-10 seconds before first validation
- **Exposure**: Unhedged position during delay
- **No immediate feedback**: Can't cancel/retry quickly

#### Better Flow (Missing):

```
create_actions_proposal()
  ↓
CreateExecutorAction  (ASYNC - orders sent)
  ↓
WAIT for order confirmations
  ↓
validate_position_hedge() IMMEDIATELY
  ↓
If valid: Add to active_funding_arbitrages
If invalid: Emergency close + alert
```

---

### ⚠️ MEDIUM #4: No Retry Logic for Failed Orders

**Location**: Missing feature

**Severity**: MEDIUM - Lost opportunities

#### Problem:

If order fails:
1. Emergency close triggered (line 787-800)
2. Position removed from active arbitrages
3. **No retry attempt!**

#### Scenarios:

**Temporary network glitch:**
- Order fails due to transient network error
- Good arbitrage opportunity lost
- Bot waits for next opportunity (may be worse)

**Exchange API rate limit:**
- Order fails: "Rate limit exceeded"
- Bot emergency closes
- Next attempt may hit same rate limit

#### Recommendation:

Add retry logic with exponential backoff:
- 1st attempt: immediate
- 2nd attempt: +500ms
- 3rd attempt: +1s
- Give up after 3 attempts

---

### ⚠️ MEDIUM #5: Partial Fills Not Rebalanced

**Location**: `scripts/v2_funding_rate_arb.py:429-498`

**Severity**: MEDIUM - Suboptimal handling

#### Current Behavior:

**Scenario:**
- OKX: Order for 1.0 BTC fills 100% (1.0 BTC long)
- Hyperliquid: Order for 1.0 BTC fills 60% (0.6 BTC short)
- Net position: 0.4 BTC long (unhedged!)

**Bot response:**
- `validate_position_hedge()` calculates imbalance: 40%
- Imbalance > 10% threshold
- Emergency close triggered (line 787)
- Both positions closed at market

#### Problems:

1. **No attempt to fill remaining 40%** on Hyperliquid
2. **Emergency close = market orders = slippage**
3. **Lost arbitrage opportunity** even though 60% filled fine

#### Better Approach:

```python
if imbalance > threshold:
    # Calculate unfilled amount
    if notional_1 > notional_2:
        unfilled_exchange = connector_2
        unfilled_amount = (notional_1 - notional_2) / price_2
    else:
        unfilled_exchange = connector_1
        unfilled_amount = (notional_2 - notional_1) / price_1

    # Try to rebalance first
    try_rebalance_order(unfilled_exchange, unfilled_amount)

    # If rebalance fails, THEN emergency close
```

---

## ✅ WHAT WORKS WELL

### 1. ✅ Comprehensive Position Validation

**Location**: `scripts/v2_funding_rate_arb.py:429-498`

```python
def validate_position_hedge(self, token: str) -> tuple[bool, str]:
```

**Checks performed:**
- ✅ Both executors exist (line 447)
- ✅ Both have filled_amount > 0 (lines 463-467)
- ✅ Prices available (lines 477-480)
- ✅ Notional values calculated correctly (lines 483-484)
- ✅ Imbalance detection with threshold (lines 490-493)
- ✅ Warning for partial imbalance (lines 495-496)

**EXCELLENT validation logic!** Problem is timing (runs too late).

### 2. ✅ Safe Trading Pair Formation

**Location**: `scripts/v2_funding_rate_arb.py:138-139`

```python
@classmethod
def get_trading_pair_for_connector(cls, token, connector):
    return f"{token}-{cls.quote_markets_map.get(connector, 'USDT')}"
```

**Good practices:**
- Uses consistent format: `TOKEN-QUOTE`
- Has default fallback: `USDT`
- Per-exchange quote currency mapping

**Note**: USDT vs USD issue is config, not code bug.

### 3. ✅ Pre-Flight Safety Checks

**Location**: `scripts/v2_funding_rate_arb.py:697-722`

Before opening positions:
- ✅ Balance validation (lines 698-701)
- ✅ Profitability calculation (lines 703-705)
- ✅ Slippage protection (lines 717-722)
- ✅ Fee consideration (in get_current_profitability_after_fees)

**Excellent risk management BEFORE execution!**

### 4. ✅ Emergency Close Mechanism

**Location**: `scripts/v2_funding_rate_arb.py:787-815`

```python
if not is_hedged:
    if self.config.emergency_close_on_imbalance:
        self.logger().error(f"EMERGENCY CLOSE for {token}: {hedge_msg}")
        # Telegram alert sent
        # Close both positions
```

**Works well for:**
- Detecting imbalances
- Alerting via Telegram
- Closing positions to limit loss

**Could improve:**
- Add rebalance attempt before emergency close
- Track emergency close count (if frequent = systematic issue)

### 5. ✅ Continuous Monitoring

**Location**: `scripts/v2_funding_rate_arb.py:783-820`

In every tick, bot checks:
- Position hedge status
- Funding rate changes
- PnL targets

**Good continuous risk management!**

---

## 📊 Risk Assessment

| Issue | Severity | Probability | Impact | Risk Score |
|-------|----------|-------------|--------|------------|
| Race condition (unhedged window) | CRITICAL | High (every trade) | $100-1000 | 🔴 9/10 |
| USDT/USD discrepancy | HIGH | Low (rare depeg) | $500-5000 | 🟡 6/10 |
| No immediate validation | MEDIUM | High | $50-200 | 🟡 5/10 |
| No retry logic | MEDIUM | Medium | Opportunity loss | 🟢 4/10 |
| No rebalance attempt | MEDIUM | Medium | $20-100 | 🟢 4/10 |

**Overall Risk Level**: 🔴 HIGH (due to Critical #1)

---

## 🎯 Priority Fixes

### Priority 1: CRITICAL - Fix Race Condition

**Must implement** before production:

```python
# Option A: Wait for executor confirmations
def create_actions_proposal(self):
    # ... existing code ...

    create_actions.extend([...])

    # DON'T add to active_funding_arbitrages here!
    # Mark as "pending" instead
    self.pending_funding_arbitrages[token] = {
        "connector_1": connector_1,
        "connector_2": connector_2,
        "executors_ids": [...]
    }

# Add new method: validate_pending_positions()
def validate_pending_positions(self):
    """Called in stop_actions_proposal FIRST"""
    for token, info in list(self.pending_funding_arbitrages.items()):
        is_valid, msg = self.validate_position_hedge_for_pending(token, info)

        if is_valid:
            # Move to active
            self.active_funding_arbitrages[token] = info
            del self.pending_funding_arbitrages[token]
            self.logger().info(f"Position validated for {token}: {msg}")
        else:
            # Emergency close if any partial fills
            self.logger().error(f"Position validation failed for {token}: {msg}")
            # ... emergency close logic ...
```

**OR Option B: Use executor callbacks** (if framework supports)

### Priority 2: HIGH - Monitor USDT Peg

```python
def check_usdt_peg(self) -> bool:
    """Check if USDT is depegged"""
    # Get USDT/USD price from oracle or exchange
    usdt_price = self.get_usdt_usd_price()

    if usdt_price is None:
        return True  # Assume OK if can't check

    depeg_threshold = Decimal("0.005")  # 0.5%
    depeg = abs(usdt_price - Decimal("1.0"))

    if depeg > depeg_threshold:
        self.logger().critical(f"USDT DEPEGGED: {usdt_price:.4f}")
        self.alerter.critical(
            "USDT Depeg Detected",
            f"USDT price: ${usdt_price:.4f}",
            {"Depeg": f"{depeg:.2%}", "Threshold": f"{depeg_threshold:.2%}"}
        )
        return False

    return True
```

### Priority 3: MEDIUM - Add Retry Logic

```python
def execute_with_retry(self, executor_config, max_retries=3):
    """Execute order with retry logic"""
    for attempt in range(max_retries):
        try:
            action = CreateExecutorAction(executor_config=executor_config)
            # Send action
            return True
        except Exception as e:
            wait_time = 0.5 * (2 ** attempt)  # Exponential backoff
            self.logger().warning(f"Order attempt {attempt+1} failed: {e}. Retrying in {wait_time}s")
            time.sleep(wait_time)

    return False  # All retries failed
```

### Priority 4: MEDIUM - Rebalance Before Emergency Close

```python
def try_rebalance_position(self, token: str, executor_1, executor_2, price_1, price_2):
    """Attempt to rebalance imbalanced position"""
    notional_1 = executor_1.filled_amount * price_1
    notional_2 = executor_2.filled_amount * price_2

    if notional_1 > notional_2:
        # Need to increase position 2
        unfilled = (notional_1 - notional_2) / price_2
        # Send limit order for unfilled amount
        # ...
    else:
        # Need to increase position 1
        unfilled = (notional_2 - notional_1) / price_1
        # ...
```

---

## 📝 Summary

### Critical Issues: 1
- Race condition causing unhedged positions

### High Issues: 1
- USDT/USD quote currency mismatch

### Medium Issues: 3
- No immediate post-execution validation
- No retry logic
- No rebalance attempts

### Total Issues: 5

### Issues Fixed: 0
### Issues Remaining: 5

---

## ✅ Recommendations

### Immediate (Before Production):
1. ✅ Fix race condition with pending positions pattern
2. ✅ Add USDT peg monitoring
3. ✅ Add immediate validation after order execution

### Short-term (First Week):
1. Add retry logic with exponential backoff
2. Implement rebalance before emergency close
3. Add metrics: emergency close count, rebalance success rate

### Long-term (First Month):
1. Consider using only USDT pairs (consistency)
2. Add order execution timeout monitoring
3. Implement smart order routing (try limit orders first, fallback to market)

---

## 🔍 Testing Recommendations

### Unit Tests Needed:

1. **Test race condition fix:**
   - Mock slow executor
   - Verify position not in active until validated
   - Verify emergency close for failed orders

2. **Test USDT depeg scenario:**
   - Mock USDT price at $0.95
   - Verify bot stops trading
   - Verify alert sent

3. **Test partial fills:**
   - Mock 100% fill on one, 50% on other
   - Verify rebalance attempted
   - Verify emergency close if rebalance fails

4. **Test network failures:**
   - Mock API timeouts
   - Verify retry logic
   - Verify alert sent after max retries

### Integration Tests Needed:

1. Test on testnet with real API calls
2. Monitor for 24 hours, check for any emergency closes
3. Simulate network issues (disconnect WiFi briefly)
4. Verify Telegram alerts received for all scenarios

---

**Audit completed. Critical issues identified. Fixes required before production deployment.**
