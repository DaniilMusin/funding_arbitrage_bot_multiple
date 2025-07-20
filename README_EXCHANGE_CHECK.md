# Проверка подключений к биржам в Hummingbot

## 🎯 Цель

Проверка и настройка подключений ко всем поддерживаемым биржам в Hummingbot.

## 📊 Результаты проверки

**Статус**: 6/8 бирж работают корректно ✅

### ✅ Работающие биржи:
- KuCoin Perpetual
- Binance Spot (через testnet)
- OKX Spot
- Kraken Spot
- Gate.io Spot
- HTX Spot

### ⚠️ Биржи с проблемами:
- Bybit Perpetual (требует специальную настройку)
- MEXC Spot (возможно, изменился API)

## 🚀 Быстрый старт

### 1. Проверка подключений

```bash
# Базовая проверка (без API ключей)
python3 final_exchange_check.py

# Полная проверка (с API ключами)
python3 check_exchange_connections.py
```

### 2. Настройка API ключей

Создайте файл `.env`:

```bash
# Пример для KuCoin
export KUCOIN_PERPETUAL_API_KEY="your_api_key"
export KUCOIN_PERPETUAL_SECRET_KEY="your_secret_key"
export KUCOIN_PERPETUAL_PASSPHRASE="your_passphrase"

# Загрузите переменные
source .env
```

### 3. Запуск Hummingbot

```bash
# Установка зависимостей
./install

# Компиляция
./compile

# Запуск
./start
```

## 📁 Файлы

- `final_exchange_check.py` - Финальная проверка подключений
- `check_exchange_connections.py` - Полная проверка с API ключами
- `exchange_connection_report.md` - Подробный отчет
- `SETUP_INSTRUCTIONS.md` - Инструкции по настройке

## 🔧 Решение проблем

### Bybit (HTTP 403)
- Требуются специальные заголовки
- Проверьте User-Agent и Referer

### Binance (Блокировка)
- Используйте VPN или прокси
- Для тестирования используйте testnet

### MEXC (HTTP 404)
- Проверьте актуальную документацию API
- Возможно, изменился URL

## 📞 Поддержка

- [Документация Hummingbot](https://hummingbot.org/docs/)
- [GitHub Hummingbot](https://github.com/hummingbot/hummingbot)

---

**Дата**: $(date)
**Статус**: 75% бирж работают корректно