# Как применить исправления

## ⚠️ ВАЖНО

Файлы `hummingbot/strategy/funding_arbitrage/funding_arbitrage_strategy.py` и `funding_scheduler.py` были изменены напрямую в рабочей директории.

Поскольку `hummingbot/` является git submodule (read-only upstream), эти изменения НЕ могут быть закоммичены в основной репозиторий.

## Вариант 1: Использовать как есть (рекомендуется для тестирования)

Изменения уже применены в вашей локальной копии. Просто запускайте бот:

```bash
python3 bin/hummingbot.py
```

## Вариант 2: Создать fork upstream

Если нужно сохранить изменения:

1. Создайте fork hummingbot репозитория
2. Примените изменения в вашем fork
3. Обновите submodule на ваш fork

## Вариант 3: Переместить код в adapters/

Создайте адаптер над upstream кодом в `adapters/` директории.

## Файлы изменены:

1. **hummingbot/strategy/funding_arbitrage/funding_arbitrage_strategy.py**
   - Реализация _place_order() - размещение реальных ордеров
   - Реализация _verify_order_filled() - проверка исполнения
   - Реализация _emergency_close() - аварийное закрытие
   - Реализация _check_hedge_gap() - проверка hedge gap
   - Переписан _execute_arbitrage() - с rollback и параллельным исполнением
   - Переписан _close_position() - реальное закрытие позиций

2. **hummingbot/strategy/funding_arbitrage/funding_scheduler.py**
   - Исправлен Hyperliquid schedule (hourly вместо 8h)

## Для production deployment:

Рекомендуется создать отдельную ветку или fork для этих изменений, чтобы они не потерялись при обновлении upstream.
