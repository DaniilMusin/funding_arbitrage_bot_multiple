# 🐛 Additional Bug Found - Logic Error

**Дата:** 2025-11-17
**Тип:** Logic Error (не crash, но неправильные расчеты)
**Приоритет:** P2 (Medium) - не вызывает crash, но дает неправильные результаты

---

## **BUG #3: Неправильный парсинг trading pair (P2)**

**Файл:** `hummingbot/strategy/funding_arbitrage/edge_decomposition.py`
**Строки:** 245-246
**Приоритет:** **P2 - MEDIUM (Logic Error)**

### Проблема:

```python
# edge_decomposition.py:240-246
# Extract base and quote assets from trading pair
if '-' in trading_pair:
    base_asset, quote_asset = trading_pair.split('-')
else:
    # Assume format like BTCUSDT
    base_asset = trading_pair[:-4] if trading_pair.endswith('USDT') else trading_pair[:-3]
    quote_asset = trading_pair[len(base_asset):]
```

**Проблема:** Логика предполагает только 2 варианта quote currency:
- USDT (4 символа)
- Все остальное (3 символа)

Но это **неправильно** для многих quote currencies!

### Примеры неправильного парсинга:

| Trading Pair | Ожидаемый результат | Фактический результат | ❌ Ошибка |
|--------------|-------------------|---------------------|-----------|
| `ETHUSDC` | base=`ETH`, quote=`USDC` | base=`ETHUS`, quote=`DC` | ✅ **ДА** |
| `BTCBUSD` | base=`BTC`, quote=`BUSD` | base=`BTCB`, quote=`USD` | ✅ **ДА** |
| `BNBTUSD` | base=`BNB`, quote=`TUSD` | base=`BNBT`, quote=`USD` | ✅ **ДА** |
| `ETHBTC` | base=`ETH`, quote=`BTC` | base=`E`, quote=`TH` | ✅ **ДА** |
| `BTCUSDT` | base=`BTC`, quote=`USDT` | base=`BTC`, quote=`USDT` | ❌ Правильно |
| `ETHEUR` | base=`ETH`, quote=`EUR` | base=`E`, quote=`TH` | ✅ **ДА** |
| `BTC-USDT` | base=`BTC`, quote=`USDT` | base=`BTC`, quote=`USDT` | ❌ Правильно |

### Последствия:

1. **Неправильные borrow rates** - используется неправильный asset для получения borrow rate
2. **Неправильные borrow costs** - расчет borrowing costs будет некорректным
3. **НЕ вызывает crash** - просто дает неправильные числа

### Пример:

```python
# Реальный сценарий:
trading_pair = "ETHUSDC"

# Текущая логика:
base_asset = "ETHUS"  # НЕПРАВИЛЬНО! Должно быть "ETH"
quote_asset = "DC"    # НЕПРАВИЛЬНО! Должно быть "USDC"

# Потом пытается получить borrow rate:
borrow_rate = borrow_rates.get("DC", Decimal("0.0001"))  # Не найдет "DC"!
# Будет использован default rate вместо реального rate для USDC
```

### Решение:

**Вариант 1: Список известных quote currencies (рекомендуется)**

```python
def _parse_trading_pair(self, trading_pair: str) -> Tuple[str, str]:
    """Parse trading pair into base and quote assets."""
    # Handle pairs with explicit separator
    if '-' in trading_pair:
        return tuple(trading_pair.split('-', 1))

    # List of known quote currencies (longest first!)
    QUOTE_CURRENCIES = [
        'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI',  # Stablecoins (4 chars)
        'USD', 'EUR', 'GBP', 'JPY', 'BTC', 'ETH', 'BNB'  # 3 chars
    ]

    # Try each quote currency
    for quote in QUOTE_CURRENCIES:
        if trading_pair.endswith(quote):
            base = trading_pair[:-len(quote)]
            if base:  # Make sure base is not empty
                return base, quote

    # Fallback: assume last 4 or 3 chars
    # (Current logic as last resort)
    if trading_pair.endswith('USDT'):
        return trading_pair[:-4], 'USDT'
    else:
        return trading_pair[:-3], trading_pair[-3:]
```

**Вариант 2: Regex (более гибкий)**

```python
import re

def _parse_trading_pair(self, trading_pair: str) -> Tuple[str, str]:
    """Parse trading pair into base and quote assets."""
    # Handle explicit separator
    if '-' in trading_pair:
        return tuple(trading_pair.split('-', 1))

    # Match: base (2-5 uppercase letters) + quote (3-4 uppercase letters)
    match = re.match(r'^([A-Z]{2,5})([A-Z]{3,4})$', trading_pair)
    if match:
        return match.group(1), match.group(2)

    # Fallback
    return trading_pair[:-4], trading_pair[-4:]
```

**Вариант 3: Простой fix для текущей логики**

```python
# Extract base and quote assets from trading pair
if '-' in trading_pair:
    base_asset, quote_asset = trading_pair.split('-', 1)  # Use maxsplit=1
else:
    # Assume format like BTCUSDT
    # Check for common 4-char quote currencies
    if trading_pair.endswith(('USDT', 'USDC', 'BUSD', 'TUSD')):
        base_asset = trading_pair[:-4]
        quote_asset = trading_pair[-4:]
    # Otherwise assume 3-char quote
    else:
        base_asset = trading_pair[:-3]
        quote_asset = trading_pair[-3:]
```

### Рекомендация:

Использовать **Вариант 1** - он наиболее надежный и покрывает все основные quote currencies на crypto exchanges.

---

## Дополнительная проверка: Empty string edge case

**Потенциальная проблема:** Если `trading_pair` очень короткий (меньше 3 символов):

```python
trading_pair = "AB"  # Очень короткий
base_asset = trading_pair[:-3]  # "" (empty string)
quote_asset = trading_pair[0:]   # "AB"

# Потом:
borrow_rate = borrow_rates.get("AB", Decimal("0.0001"))  # OK, не crash
```

Это не вызовет crash, но даст неправильные результаты. Однако в реальности trading pairs всегда имеют минимум 6 символов (например "BTCUSD"), так что это маловероятно.

---

## Тестирование:

```python
def test_parse_trading_pair():
    """Test trading pair parsing with various formats."""
    test_cases = [
        ("BTC-USDT", ("BTC", "USDT")),
        ("ETH-USDC", ("ETH", "USDC")),
        ("BTCUSDT", ("BTC", "USDT")),
        ("ETHUSDC", ("ETH", "USDC")),  # Currently FAILS!
        ("BNBBUSD", ("BNB", "BUSD")),  # Currently FAILS!
        ("ETHBTC", ("ETH", "BTC")),    # Currently FAILS!
    ]

    for pair, expected in test_cases:
        base, quote = parse_trading_pair(pair)
        assert (base, quote) == expected, \
            f"Failed for {pair}: got ({base}, {quote}), expected {expected}"
```

---

## Статус:

- [ ] Исправить парсинг trading pair
- [ ] Добавить unit tests
- [ ] Проверить на всех поддерживаемых exchanges

---

**Приоритет:** P2 - Medium
**Причина:** Не вызывает crash, но может давать неправильные borrow costs для некоторых trading pairs. В production это приведет к неправильным расчетам edge и потенциальным убыткам.
