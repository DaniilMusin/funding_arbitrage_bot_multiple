# Инструкции по настройке подключений к биржам в Hummingbot

## 📊 Текущий статус подключений

### ✅ Работающие биржи (6/8):
- **KuCoin Perpetual** - ✅ Готов к использованию
- **Binance Spot** - ✅ Готов к использованию (через testnet)
- **OKX Spot** - ✅ Готов к использованию
- **Kraken Spot** - ✅ Готов к использованию
- **Gate.io Spot** - ✅ Готов к использованию
- **HTX Spot** - ✅ Готов к использованию

### ⚠️ Биржи с проблемами (2/8):
- **Bybit Perpetual** - ❌ Требуется специальная настройка
- **MEXC Spot** - ❌ Возможно, изменился API

## 🔧 Пошаговая настройка

### 1. Установка зависимостей

```bash
# Установка основных зависимостей
pip install aiohttp --break-system-packages

# Для работы с Kraken (если нужно)
pip install Brotli --break-system-packages
```

### 2. Настройка API ключей

Создайте файл `.env` в корне проекта:

```bash
# Bybit
export BYBIT_PERPETUAL_API_KEY="your_bybit_api_key"
export BYBIT_PERPETUAL_SECRET_KEY="your_bybit_secret_key"

# KuCoin
export KUCOIN_PERPETUAL_API_KEY="your_kucoin_api_key"
export KUCOIN_PERPETUAL_SECRET_KEY="your_kucoin_secret_key"
export KUCOIN_PERPETUAL_PASSPHRASE="your_kucoin_passphrase"

# Binance
export BINANCE_API_KEY="your_binance_api_key"
export BINANCE_API_SECRET="your_binance_secret_key"

# OKX
export OKX_API_KEY="your_okx_api_key"
export OKX_SECRET_KEY="your_okx_secret_key"
export OKX_PASSPHRASE="your_okx_passphrase"

# Kraken
export KRAKEN_API_KEY="your_kraken_api_key"
export KRAKEN_SECRET_KEY="your_kraken_secret_key"

# Gate.io
export GATE_IO_API_KEY="your_gateio_api_key"
export GATE_IO_SECRET_KEY="your_gateio_secret_key"

# HTX
export HTX_API_KEY="your_htx_api_key"
export HTX_SECRET_KEY="your_htx_secret_key"
```

### 3. Загрузка переменных окружения

```bash
# Загрузите переменные окружения
source .env

# Или добавьте в ~/.bashrc для постоянной загрузки
echo "source /path/to/your/project/.env" >> ~/.bashrc
```

### 4. Проверка подключений

```bash
# Базовая проверка (без API ключей)
python3 final_exchange_check.py

# При необходимости можно указать прокси, например:
export PROXY="socks5://localhost:9050"
python3 final_exchange_check.py

# Полная проверка (с API ключами)
python3 check_exchange_connections.py
```

## 📁 Структура конфигурации

### Текущие файлы конфигурации:

```
conf/
├── global_conf.yml              # Глобальные настройки
├── funding_rate_arb.yml         # Настройки стратегии
├── connectors/                  # Настройки коннекторов (пустая)
└── strategies/                  # Настройки стратегий (пустая)
```

### Настройка стратегии funding rate arbitrage:

```yaml
# conf/funding_rate_arb.yml
min_funding_rate_profitability: 0.0005  # Минимальная прибыльность
position_size_quote: 100                # Размер позиции в USDT
leverage: 5                             # Плечо
connectors:
  - bybit_perpetual                     # Поддерживаемые биржи
  - kucoin_perpetual
tokens:
  - BTC                                 # Торгуемые токены
  - ETH
```

## 🚀 Запуск Hummingbot

### 1. Компиляция (если нужно)

```bash
# Установка зависимостей для компиляции
./install

# Компиляция
./compile
```

### 2. Запуск

```bash
# Запуск Hummingbot
./start

# Или через Python
python3 bin/hummingbot.py
```

### 3. Настройка стратегии

В консоли Hummingbot:

```bash
# Импорт стратегии
import conf/funding_rate_arb.yml

# Настройка коннекторов
connect bybit_perpetual
connect kucoin_perpetual

# Запуск стратегии
start
```

## 🔍 Мониторинг и диагностика

### 1. Логи

```bash
# Просмотр логов
tail -f logs/hummingbot.log

# Логи коннекторов
tail -f logs/bybit_perpetual.log
tail -f logs/kucoin_perpetual.log
```

### 2. Проверка статуса

```bash
# Проверка подключений
python3 final_exchange_check.py

# Проверка балансов (требует API ключи)
python3 check_exchange_connections.py
```

### 3. Тестирование API

```bash
# Тест Bybit API
curl -H "User-Agent: Mozilla/5.0" https://api.bybit.com/v5/market/time

# Тест KuCoin API
curl https://api-futures.kucoin.com/api/v1/timestamp

# Тест Binance API
curl https://testnet.binance.vision/api/v3/time
```

## ⚠️ Решение проблем

### Bybit Perpetual (HTTP 403)

**Проблема**: Требуются специальные заголовки

**Решение**:
1. Добавьте правильный User-Agent
2. Используйте Referer заголовок
3. Проверьте IP-адрес (возможна блокировка по региону)

```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Referer': 'https://www.bybit.com/',
}
```

### Binance (Географическая блокировка)

**Проблема**: Блокировка по региону

**Решение**:
1. Используйте VPN
2. Используйте прокси
3. Используйте testnet для тестирования

### MEXC (HTTP 404)

**Проблема**: Изменился URL API

**Решение**:
1. Проверьте актуальную документацию MEXC
2. Обновите URL в конфигурации
3. Обратитесь в поддержку MEXC

## 📞 Поддержка

### Полезные ссылки:

- [Документация Hummingbot](https://hummingbot.org/docs/)
- [GitHub Hummingbot](https://github.com/hummingbot/hummingbot)
- [Discord Hummingbot](https://discord.gg/hummingbot)

### Создание issue:

1. Проверьте существующие issues
2. Создайте новый issue с подробным описанием проблемы
3. Приложите логи и конфигурацию
4. Укажите версию Hummingbot и ОС

## 🔒 Безопасность

### Рекомендации:

1. **Никогда не храните API ключи в коде**
2. Используйте переменные окружения
3. Регулярно обновляйте API ключи
4. Используйте минимальные разрешения для API ключей
5. Мониторьте активность аккаунтов

### Создание API ключей:

1. **Bybit**: Только чтение и торговля, без вывода
2. **KuCoin**: Только чтение и торговля, без вывода
3. **Binance**: Только чтение и торговля, без вывода
4. **OKX**: Только чтение и торговля, без вывода
5. **Kraken**: Только чтение и торговля, без вывода
6. **Gate.io**: Только чтение и торговля, без вывода
7. **HTX**: Только чтение и торговля, без вывода

---

**Дата создания**: $(date)
**Версия Hummingbot**: $(cat hummingbot/VERSION)
**Статус**: 6/8 бирж работают корректно