# Guide: Добавление новых бирж в Funding Arbitrage Bot

## Дата: 2025-11-13

Этот guide описывает как легко добавить новую биржу в бот для funding arbitrage.

---

## 🎯 АРХИТЕКТУРА ПОДДЕРЖКИ БИРЖ

Бот спроектирован для **легкого масштабирования** и добавления новых бирж. Вся exchange-specific логика централизована в двух mapping структурах.

### Ключевые принципы:

1. **No hardcoded logic** - нет специального кода для конкретных бирж
2. **Mapping-based configuration** - все особенности бирж в mappings
3. **Fallback defaults** - для неизвестных бирж используются дефолты
4. **Connector agnostic** - основная логика не зависит от биржи

---

## ✅ УЖЕ ПОДДЕРЖИВАЮТСЯ (preonfigured):

Следующие биржи **уже настроены** и готовы к использованию:

| Биржа | Connector Name | Quote Asset | Funding Interval | Status |
|-------|---------------|-------------|------------------|--------|
| **Hyperliquid** | hyperliquid_perpetual | USD | 1 hour | ✅ Tested |
| **OKX** | okx_perpetual | USDT | 8 hours | ✅ Tested |
| **Binance** | binance_perpetual | USDT | 8 hours | ✅ Ready |
| **Bybit** | bybit_perpetual | USDT | 8 hours | ✅ Ready |
| **Gate.io** | gate_io_perpetual | USDT | 8 hours | ✅ Ready |
| **KuCoin** | kucoin_perpetual | USDT | 8 hours | ✅ Ready |
| **BingX** | bingx_perpetual | USDT | 8 hours | ✅ Ready |
| **Bitget** | bitget_perpetual | USDT | 8 hours | ✅ Ready |
| **MEXC** | mexc_perpetual | USDT | 8 hours | ✅ Ready |
| **Phemex** | phemex_perpetual | USDT | 8 hours | ✅ Ready |

**Чтобы использовать:** Просто добавьте connector_name в конфигурацию!

---

## 📝 КАК ДОБАВИТЬ НОВУЮ БИРЖУ:

### Шаг 1: Проверить наличие connector в Hummingbot

**Важно:** Биржа должна иметь готовый perpetual connector в Hummingbot!

Проверить наличие:
```bash
ls hummingbot/connector/derivative/
```

Или посмотреть список на: https://hummingbot.org/exchanges/

**Требования к connector:**
- ✅ Поддержка perpetual futures
- ✅ Поддержка funding rate API
- ✅ Поддержка leverage
- ✅ Поддержка hedge mode (желательно)

---

### Шаг 2: Узнать параметры биржи

Нужно узнать 2 параметра:

#### A) Quote Asset (что используется для margin)

Обычно:
- **USDT** - большинство бирж (Binance, OKX, Bybit, etc.)
- **USD** - Hyperliquid, некоторые другие
- **USDC** - некоторые биржи

Как узнать: проверить документацию биржи или посмотреть trading pairs (BTC-USDT, ETH-USDT → USDT)

#### B) Funding Rate Interval (как часто выплачивается funding)

Обычно:
- **8 hours** - стандарт для большинства бирж (Binance, OKX, Bybit, Gate.io, etc.)
- **1 hour** - Hyperliquid, Drift Protocol
- **4 hours** - некоторые DeFi protocols

Как узнать: проверить документацию биржи в разделе "Funding Rate"

---

### Шаг 3: Добавить в mappings

Откройте файл: `scripts/v2_funding_rate_arb.py`

Найдите класс `FundingRateArbitrage` и добавьте биржу в **оба mapping**:

```python
class FundingRateArbitrage(StrategyV2Base):
    quote_markets_map = {
        # ... existing exchanges ...
        "NEW_EXCHANGE_perpetual": "USDT",  # ← Добавить сюда
    }
    funding_payment_interval_map = {
        # ... existing exchanges ...
        "NEW_EXCHANGE_perpetual": 60 * 60 * 8,  # 8 hours ← Добавить сюда
    }
```

**Формат connector_name:**
- Обычно: `{exchange_name}_perpetual`
- Примеры: `binance_perpetual`, `okx_perpetual`, `gate_io_perpetual`
- Важно: имя должно совпадать с именем connector в Hummingbot!

**Значение funding interval:**
```python
60 * 60 * 1   # 1 hour = 3600 seconds
60 * 60 * 4   # 4 hours = 14400 seconds
60 * 60 * 8   # 8 hours = 28800 seconds (стандарт)
60 * 60 * 12  # 12 hours = 43200 seconds
```

---

### Шаг 4: Настроить API credentials

Создайте API keys на бирже с permissions:
- ✅ Read (market data, positions)
- ✅ Trade (open/close positions)
- ⚠️ NO Withdrawal (не нужно!)

Добавьте credentials в Hummingbot:
```bash
connect NEW_EXCHANGE_perpetual
```

Или в конфиг файле (зависит от настройки Hummingbot).

---

### Шаг 5: Добавить в конфигурацию

Откройте: `conf/funding_rate_arb.yml`

Добавьте биржу в список connectors:

```yaml
connectors:
  - okx_perpetual
  - hyperliquid_perpetual
  - binance_perpetual      # ← Добавить новую
```

---

### Шаг 6: Протестировать подключение

Проверьте что биржа работает:

```python
# test_new_exchange.py
import asyncio
from hummingbot.connector.derivative.NEW_EXCHANGE_perpetual import ...

async def test():
    # Test connection
    # Test funding rates
    # Test balances
    pass

asyncio.run(test())
```

Или используйте существующий тестовый скрипт:
```bash
python test_okx_hyperliquid_connection.py  # Модифицировать для новой биржи
```

---

### Шаг 7: Запустить бота

```bash
# Paper trading mode для теста
docker-compose --profile paper up -d

# Production mode (после успешного теста)
docker-compose --profile prod up -d
```

Мониторить логи:
```bash
docker-compose logs -f
```

---

## 🎯 ПРИМЕРЫ ДОБАВЛЕНИЯ:

### Пример 1: Добавить Binance Futures

**Уже готово!** Binance уже pre-configured. Просто добавьте в config:

```yaml
# conf/funding_rate_arb.yml
connectors:
  - okx_perpetual
  - hyperliquid_perpetual
  - binance_perpetual  # ← Добавить
```

Настройте API keys:
```bash
connect binance_perpetual
```

**Готово!** 🎉

---

### Пример 2: Добавить новую биржу (Deribit)

**Шаг 1:** Проверить что connector существует
```bash
ls hummingbot/connector/derivative/deribit_perpetual
# Если есть → продолжаем
```

**Шаг 2:** Узнать параметры
- Quote asset: **USD** (из документации Deribit)
- Funding interval: **8 hours** (из документации)

**Шаг 3:** Добавить в code:
```python
# scripts/v2_funding_rate_arb.py

quote_markets_map = {
    # ... existing ...
    "deribit_perpetual": "USD",  # ← Добавить
}

funding_payment_interval_map = {
    # ... existing ...
    "deribit_perpetual": 60 * 60 * 8,  # 8 hours ← Добавить
}
```

**Шаг 4:** Настроить credentials
```bash
connect deribit_perpetual
```

**Шаг 5:** Добавить в config
```yaml
connectors:
  - okx_perpetual
  - hyperliquid_perpetual
  - deribit_perpetual  # ← Добавить
```

**Шаг 6:** Закоммитить изменения
```bash
git add scripts/v2_funding_rate_arb.py conf/funding_rate_arb.yml
git commit -m "Add Deribit perpetual support"
git push
```

**Готово!** 🎉

---

## 🚀 МАСШТАБИРОВАНИЕ НА МНОГО БИРЖ:

### Сценарий: 6 бирж одновременно

```yaml
# conf/funding_rate_arb.yml

connectors:
  - okx_perpetual         # Pair 1
  - hyperliquid_perpetual # Pair 1
  - binance_perpetual     # Pair 2
  - bybit_perpetual       # Pair 2
  - gate_io_perpetual     # Pair 3
  - kucoin_perpetual      # Pair 3
```

**Результат:**
- С 6 коннекторами → **3 пары одновременно!**
- 3× profit potential! 🚀

**Важно:**
- Каждая пара требует достаточный balance на обеих биржах
- Мониторить все позиции
- Больше risk exposure (но diversified!)

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ:

### 1. Position Mode

Некоторые биржи требуют разный position mode:

```python
# scripts/v2_funding_rate_arb.py, apply_initial_setting()

def apply_initial_setting(self):
    for connector_name, connector in self.connectors.items():
        if self.is_perpetual(connector_name):
            # Hyperliquid uses ONEWAY, others use HEDGE
            position_mode = PositionMode.ONEWAY if connector_name == "hyperliquid_perpetual" else PositionMode.HEDGE
            connector.set_position_mode(position_mode)
```

**Если новая биржа требует ONEWAY:**
```python
position_mode = PositionMode.ONEWAY if connector_name in ["hyperliquid_perpetual", "NEW_EXCHANGE"] else PositionMode.HEDGE
```

### 2. Different Quote Assets

Если биржа использует другой quote asset (не USDT/USD):

```python
quote_markets_map = {
    "NEW_EXCHANGE_perpetual": "BUSD",  # Или USDC, или другой
}
```

Бот автоматически адаптируется!

### 3. Different Funding Intervals

Если биржа использует нестандартный interval:

```python
funding_payment_interval_map = {
    "NEW_EXCHANGE_perpetual": 60 * 60 * 4,  # 4 hours
}
```

Нормализация происходит автоматически в `get_normalized_funding_rate_in_seconds()`!

### 4. Trading Pair Format

Некоторые биржи используют другой формат:
- Стандарт: `BTC-USDT`
- Некоторые: `BTCUSDT` (без тире)
- Hyperliquid: `BTC-USD`

Бот автоматически формирует правильный формат через `get_trading_pair_for_connector()`:

```python
def get_trading_pair_for_connector(cls, token, connector):
    return f"{token}-{cls.quote_markets_map.get(connector, 'USDT')}"
```

Если нужен другой формат, можно добавить special case.

---

## 📊 CHECKING COMPATIBILITY:

### Checklist для новой биржи:

- [ ] Connector существует в Hummingbot
- [ ] Perpetual futures поддерживаются
- [ ] Funding rate API доступен
- [ ] Известен quote asset (USDT/USD/etc)
- [ ] Известен funding interval (обычно 8 hours)
- [ ] API keys созданы (read + trade permissions)
- [ ] Connector добавлен в mappings
- [ ] Connector добавлен в config
- [ ] Credentials настроены
- [ ] Тестовое подключение успешно
- [ ] Balance достаточный для trading

---

## 🎓 BEST PRACTICES:

### 1. Начинать с малых сумм
При добавлении новой биржи:
```yaml
position_size_quote: 50-100  # Малая сумма для теста
```

### 2. Тестировать в paper mode
```bash
docker-compose --profile paper up -d
```

### 3. Мониторить первые 24-48 часов
- Проверять логи каждые 2-4 часа
- Убедиться что позиции открываются корректно
- Проверить что hedge работает

### 4. Постепенно увеличивать
- После успешного теста 2-3 дня
- Увеличить position_size_quote
- Добавить больше токенов

### 5. Diversification
С несколькими биржами:
- Не держать все средства на одной бирже
- Распределить risk
- Разные token pairs на разных биржах

---

## 🛡️ БЕЗОПАСНОСТЬ:

### API Keys Best Practices:

1. **Minimal Permissions**
   - ✅ Read market data
   - ✅ Trade (open/close positions)
   - ❌ NO Withdrawal!
   - ❌ NO Transfer!

2. **IP Whitelist**
   - Добавить IP сервера в whitelist
   - Блокирует access с других IP

3. **Separate Keys**
   - Разные API keys для разных бирж
   - Не использовать один key везде

4. **Regular Rotation**
   - Менять API keys каждые 1-3 месяца
   - Особенно после любого security incident

---

## 💡 TROUBLESHOOTING:

### Проблема: Connector not found

```
Error: No module named 'hummingbot.connector.derivative.NEW_EXCHANGE_perpetual'
```

**Решение:**
- Проверить что connector существует в Hummingbot
- Проверить правильность имени connector
- Возможно нужно обновить Hummingbot

---

### Проблема: Invalid trading pair

```
Error: Trading pair BTC-USDT not found on NEW_EXCHANGE
```

**Решение:**
- Проверить format trading pair на бирже
- Может использоваться BTCUSDT без тире
- Проверить что token поддерживается биржей

---

### Проблема: Funding rate not available

```
Warning: Error getting funding info for BTC on NEW_EXCHANGE
```

**Решение:**
- Проверить что биржа поддерживает funding rate API
- Проверить что token имеет perpetual contract
- Проверить connector реализацию

---

## 📚 РЕСУРСЫ:

### Документация бирж по funding rates:

- **Binance:** https://www.binance.com/en/support/faq/funding-fees
- **Bybit:** https://www.bybit.com/en-US/help-center/s/article/Funding-Rate
- **OKX:** https://www.okx.com/support/hc/en-us/articles/360039261134
- **Gate.io:** https://www.gate.io/help/futures/perpetual/21246
- **KuCoin:** https://www.kucoin.com/support/360015207073
- **Hyperliquid:** https://hyperliquid.gitbook.io/hyperliquid-docs/trading/perpetuals

### Hummingbot Documentation:

- **Connectors:** https://hummingbot.org/exchanges/
- **Strategy V2:** https://hummingbot.org/strategies/
- **API Setup:** https://hummingbot.org/installation/api-keys/

---

## ✅ SUMMARY:

### Добавление новой биржи = 3 простых шага:

1. **Добавить в mappings** (2 строки кода)
   ```python
   quote_markets_map = {"NEW_EXCHANGE": "USDT"}
   funding_payment_interval_map = {"NEW_EXCHANGE": 60*60*8}
   ```

2. **Добавить в config** (1 строка)
   ```yaml
   connectors: [okx_perpetual, NEW_EXCHANGE]
   ```

3. **Настроить API keys**
   ```bash
   connect NEW_EXCHANGE
   ```

**Готово!** Бот автоматически:
- ✅ Подтянет funding rates
- ✅ Нормализует intervals
- ✅ Откроет hedged позиции
- ✅ Будет мониторить hedge
- ✅ Закроет при profit/loss

---

## 🚀 ROADMAP:

### Планы на будущее:

**Phase 1 (Current):**
- ✅ OKX + Hyperliquid (working)
- ✅ 10 exchanges pre-configured

**Phase 2 (Next):**
- [ ] Add Binance + Bybit (easy - just config change)
- [ ] Test with 4 exchanges simultaneously
- [ ] Optimize token selection

**Phase 3 (Future):**
- [ ] Add Gate.io + KuCoin (more liquidity)
- [ ] Support 6-8 exchanges
- [ ] Advanced strategies (limit orders)

**Phase 4 (Advanced):**
- [ ] DeFi protocols (Drift, etc.)
- [ ] Cross-chain arbitrage
- [ ] ML-based opportunity detection

---

**Дата создания:** 2025-11-13
**Версия:** 1.0
**Статус:** ✅ PRODUCTION READY

**P.S.:** С текущей архитектурой добавление новой биржи занимает **< 5 минут!** 🚀
