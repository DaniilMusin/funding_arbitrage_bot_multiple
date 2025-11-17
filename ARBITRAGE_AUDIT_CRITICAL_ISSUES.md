# 🔴 КРИТИЧЕСКИЙ АУДИТ: Логика арбитража и вход в сделки

**Дата аудита:** 2025-11-16
**Статус:** НАЙДЕНЫ КРИТИЧЕСКИЕ ПРОБЛЕМЫ
**Рекомендация:** НЕ ЗАПУСКАТЬ В PROD до исправления

---

## 🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (P0 - исправить немедленно)

### 1. ❌ **ОРДЕРА НЕ РАЗМЕЩАЮТСЯ НА БИРЖАХ**

**Файл:** `hummingbot/strategy/funding_arbitrage/funding_arbitrage_strategy.py:469-485`

**Проблема:**
```python
async def _place_order(self, connector, trading_pair, is_buy, amount) -> str:
    """Place order on exchange."""
    # This is a simplified version - real implementation would be more sophisticated
    order_type = OrderType.MARKET
    trade_type = TradeType.BUY if is_buy else TradeType.SELL

    # Place the order (this would need proper implementation based on connector type)
    order_id = f"order_{int(time.time())}"

    # In real implementation, would call:
    # order_id = connector.buy() or connector.sell()

    return order_id  # ← ВОЗВРАЩАЕТ ФЕЙКОВЫЙ ID!
```

**Последствия:**
- Бот НЕ размещает реальные ордера
- Создает иллюзию работы без фактической торговли
- Отслеживание позиций работает с фантомными ордерами

**Решение:**
```python
async def _place_order(self, connector, trading_pair, is_buy, amount) -> str:
    """Place order on exchange."""
    try:
        if is_buy:
            order_id = await connector.buy(
                trading_pair=trading_pair,
                amount=amount,
                order_type=OrderType.MARKET,
                price=None  # Market order
            )
        else:
            order_id = await connector.sell(
                trading_pair=trading_pair,
                amount=amount,
                order_type=OrderType.MARKET,
                price=None
            )

        # Wait for order confirmation
        await self._wait_for_order_fill(connector, order_id, timeout=30)

        return order_id
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise
```

---

### 2. ❌ **НЕТ ПРОВЕРКИ УСПЕШНОСТИ ИСПОЛНЕНИЯ**

**Файл:** `hummingbot/strategy/funding_arbitrage/funding_arbitrage_strategy.py:398-467`

**Проблема:**
```python
# Execute long position
long_order_id = await self._place_order(
    long_connector, trading_pair, True, edge.notional_amount
)

# Execute short position
short_order_id = await self._place_order(
    short_connector, trading_pair, False, edge.notional_amount
)
# ← НЕТ ПРОВЕРКИ что ордера исполнились!
```

**Последствия:**
- Если первый ордер исполнился, а второй НЕТ → НЕ ХЕДЖИРОВАННАЯ ПОЗИЦИЯ
- Направленный риск вместо рыночно-нейтральной позиции
- Возможны огромные убытки при движении цены

**Решение:**
```python
async def _execute_arbitrage(self, opportunity: Dict):
    # ...
    try:
        # Execute long position
        long_order_id = await self._place_order(...)
        long_filled = await self._verify_order_filled(long_connector, long_order_id)

        if not long_filled:
            raise Exception("Long order not filled")

        # Execute short position
        try:
            short_order_id = await self._place_order(...)
            short_filled = await self._verify_order_filled(short_connector, short_order_id)

            if not short_filled:
                # ROLLBACK: Close long position immediately
                await self._emergency_close(long_connector, trading_pair, long_order_id)
                raise Exception("Short order not filled, rolled back long")

        except Exception as e:
            # Emergency close long if short failed
            await self._emergency_close(long_connector, trading_pair, long_order_id)
            raise

    except Exception as e:
        logger.error(f"Arbitrage execution failed: {e}")
        return  # Don't track failed positions
```

---

### 3. ⚠️ **НЕПРАВИЛЬНЫЙ РАСЧЕТ FUNDING DIFF ДЛЯ НЕКОТОРЫХ СТРАТЕГИЙ**

**Файл:** `hummingbot/strategy/funding_arbitrage/edge_decomposition.py:142`

**Проблема:**
```python
# Calculate expected funding PnL
funding_diff = funding_rate_short - funding_rate_long
expected_funding_pnl = funding_diff * notional_amount
```

**Контекст:**
- Если `long_exchange` платит ОТРИЦАТЕЛЬНЫЙ rate (-0.01%)
- И `short_exchange` платит ПОЛОЖИТЕЛЬНЫЙ rate (+0.05%)
- Тогда: `funding_diff = 0.05 - (-0.01) = 0.06%` ✅ ПРАВИЛЬНО

НО если стратегия:
- `long_exchange` (мы держим LONG) с rate +0.05% → МЫ ПЛАТИМ 0.05%
- `short_exchange` (мы держим SHORT) с rate -0.01% → МЫ ПОЛУЧАЕМ 0.01%

Формула правильная для **perpetual-perpetual** арбитража.

**НО:** Код предполагает что мы ВСЕГДА:
- Лонгуем на бирже с МЕНЬШИМ funding rate
- Шортим на бирже с БОЛЬШИМ funding rate

Это **ПРАВИЛЬНО** только если:
```
short_rate > long_rate  (т.е. funding_diff > 0)
```

**Решение:** Добавить проверку направления:
```python
# В funding_arbitrage_strategy.py:243
for long_ex, short_ex in opportunities:
    long_rate = funding_rates[long_ex].rate
    short_rate = funding_rates[short_ex].rate

    # Skip if funding rate difference is too small or wrong direction
    rate_diff = short_rate - long_rate
    if rate_diff < self.config.min_funding_rate_diff:  # ← Проверяет только размер
        continue

    # ✅ ДОБАВИТЬ: проверку что rate_diff > 0
    # Иначе мы будем терять деньги на funding
```

---

### 4. ⚠️ **HYPERLIQUID ИМЕЕТ HOURLY FUNDING, НЕ 8H**

**Файл:** `hummingbot/strategy/funding_arbitrage/funding_scheduler.py:135-145`

**Проблема:**
```python
# Hyperliquid: 00:00, 08:00, 16:00 UTC (assuming same as others)
schedules['hyperliquid'] = ExchangeSchedule(
    exchange_name='hyperliquid',
    settlement_times=[
        SettlementTime(0, 0, 'UTC'),
        SettlementTime(8, 0, 'UTC'),
        SettlementTime(16, 0, 'UTC'),
    ],
    # ...
)
```

**Факт:** Hyperliquid использует **HOURLY funding** (каждый час, а не каждые 8 часов).

**Последствия:**
- Бот может открыть позицию за 1 минуту до funding settlement
- Не успеет получить funding payment
- Потеряет деньги на комиссиях

**Решение:**
```python
# Hyperliquid: HOURLY funding (00:00, 01:00, 02:00, ... 23:00 UTC)
schedules['hyperliquid'] = ExchangeSchedule(
    exchange_name='hyperliquid',
    settlement_times=[
        SettlementTime(hour, 0, 'UTC') for hour in range(24)
    ],
    pre_settlement_buffer_minutes=3,  # Закрывать за 3 мин до settlement
    post_settlement_delay_minutes=2,
)

schedules['hyperliquid_perpetual'] = schedules['hyperliquid']
```

---

## 🟡 ВАЖНЫЕ ПРОБЛЕМЫ (P1 - исправить до production)

### 5. ⚠️ **НЕТ АТОМАРНОСТИ ХЕДЖА**

**Проблема:** Между открытием long и short позиций проходит время (возможно секунды).

**Последствия:**
- Цена может измениться между ордерами
- Размеры позиций могут не совпадать из-за slippage
- Не идеальный хедж → остаточный риск

**Решение:**
- Использовать `asyncio.gather()` для параллельного исполнения
- Добавить проверку hedge gap после исполнения
- Закрывать позиции если gap > 5%

### 6. ⚠️ **НЕТ ОБРАБОТКИ ЧАСТИЧНОГО ИСПОЛНЕНИЯ**

**Проблема:** Market ордер может исполниться частично из-за недостаточной ликвидности.

**Решение:**
```python
async def _verify_order_filled(self, connector, order_id, min_fill_ratio=0.95):
    """Verify order filled at least min_fill_ratio."""
    order = await connector.get_order(order_id)

    fill_ratio = order.executed_amount / order.amount

    if fill_ratio < min_fill_ratio:
        logger.warning(f"Order {order_id} only {fill_ratio:.1%} filled")
        return False

    return True
```

### 7. ⚠️ **НЕТ ЗАКРЫТИЯ ПОЗИЦИЙ**

**Файл:** `funding_arbitrage_strategy.py:509-537`

**Проблема:**
```python
async def _close_position(self, position_id: str, reason: str):
    # ...
    # Close long position
    long_connector = self.exchanges[position_data['long_exchange']]
    # await long_connector.sell(...)  # Close long  ← ЗАКОММЕНТИРОВАНО!

    # Close short position
    short_connector = self.exchanges[position_data['short_exchange']]
    # await short_connector.buy(...)  # Close short  ← ЗАКОММЕНТИРОВАНО!
```

**Решение:** Реализовать реальное закрытие позиций.

---

## 🟢 ПРАВИЛЬНЫЕ ЧАСТИ (что работает хорошо)

### ✅ Edge Calculation Logic
Формула расчета edge **КОРРЕКТНА**:
```
total_edge = expected_funding_pnl
           - trading_fees_total
           - borrow_cost_total
           - slippage_buffer_total
           - settlement_buffer
```

Учитывает все важные компоненты:
- ✅ Разница в funding rates
- ✅ Торговые комиссии (открытие + закрытие)
- ✅ Стоимость заимствования для leverage
- ✅ Буфер на slippage
- ✅ Буфер на изменение funding rate

### ✅ Risk Management
Проверки лимитов **ХОРОШИЕ**:
- ✅ Максимальный notional на биржу
- ✅ Максимальный leverage
- ✅ Проверка ликвидности
- ✅ Концентрация в одной паре
- ✅ Hedge gap monitoring

### ✅ Timing Logic
Логика выбора времени **КОРРЕКТНА**:
- ✅ Не открывает позиции перед settlement
- ✅ Проверяет минимальный time horizon
- ✅ Учитывает буферы для разных бирж

---

## 📋 РЕКОМЕНДАЦИИ ПО ИСПРАВЛЕНИЮ

### Приоритет 1 (КРИТИЧНО):
1. ✅ Реализовать реальное размещение ордеров в `_place_order()`
2. ✅ Добавить проверку успешности исполнения ордеров
3. ✅ Реализовать rollback при частичном провале хеджа
4. ✅ Исправить funding schedule для Hyperliquid

### Приоритет 2 (ВАЖНО):
5. ✅ Реализовать закрытие позиций в `_close_position()`
6. ✅ Добавить параллельное исполнение ордеров
7. ✅ Добавить проверку hedge gap после открытия
8. ✅ Обработка частичного исполнения

### Приоритет 3 (ЖЕЛАТЕЛЬНО):
9. ✅ Добавить мониторинг реального PnL
10. ✅ Добавить alerts на Telegram при проблемах
11. ✅ Логирование всех решений о входе/выходе
12. ✅ Backtesting на исторических данных

---

## 🧪 ТЕСТОВЫЙ ПЛАН

Перед запуском в PROD:

1. **Unit тесты:**
   - ✅ Edge calculation с разными сценариями
   - ✅ Risk limits проверки
   - ✅ Timing logic для всех бирж

2. **Integration тесты:**
   - ✅ Размещение реальных ордеров на testnet
   - ✅ Проверка rollback при ошибках
   - ✅ Проверка hedge gap после исполнения

3. **Paper trading:**
   - ✅ Минимум 7 дней непрерывной работы
   - ✅ Проверка всех edge cases
   - ✅ Мониторинг логов на ошибки

4. **Prod с минимальными суммами:**
   - ✅ Начать с $50 per position
   - ✅ 3 дня мониторинга
   - ✅ Постепенное увеличение размера

---

## 🔐 SECURITY ЧЕКЛИСТ

- [ ] API ключи имеют ТОЛЬКО права Trade + Read (НЕ Withdraw)
- [ ] .env файл в .gitignore
- [ ] Установлены максимальные лимиты на позицию
- [ ] Настроены alerts на критические события
- [ ] Backup план на случай сбоя биржи
- [ ] Tested emergency shutdown procedure

---

## 📞 ДЕЙСТВИЯ

**НЕМЕДЛЕННО:**
1. ❌ **НЕ ЗАПУСКАТЬ БОТ** до исправления критических проблем
2. ✅ Исправить _place_order() и _close_position()
3. ✅ Добавить проверки исполнения
4. ✅ Исправить Hyperliquid schedule

**ПОСЛЕ ИСПРАВЛЕНИЯ:**
1. ✅ Написать unit тесты
2. ✅ Протестировать на testnet
3. ✅ Paper trading 7 дней
4. ✅ Prod с минимальными суммами

---

**⚠️ ВАЖНО:** Этот бот находится в стадии разработки. Код арбитражной логики хороший, но **критически важные части исполнения не реализованы**. Требуется доработка перед использованием с реальными деньгами.
