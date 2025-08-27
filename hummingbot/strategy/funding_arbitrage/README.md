# Funding Arbitrage Strategy

Рынкоспецифичная логика funding arbitrage с полным управлением рисками и прозрачностью edge-расчётов.

## Ключевые возможности

### 🎯 Edge Decomposition (Разложение рентабельности)
- **Прозрачный расчёт**: `expected_funding - fees - borrow_cost - slippage_buffer >= min_edge`
- **Детальная декомпозиция**: видно каждый компонент, влияющий на прибыльность
- **История решений**: почему вошли или не вошли в позицию
- **Адаптивные буферы**: учёт рыночных условий и волатильности

### ⏰ Funding Settlement Scheduler
- **Точные временные окна**: знание settlement times по всем биржам
- **Часовые пояса**: правильная обработка UTC и локальных времён
- **Закрывашка**: автоматическое закрытие за T минут до/после settlement
- **Безопасные окна**: определение когда можно открывать новые позиции

### 🛡️ Risk Management System
- **Лимиты по биржам**: notional per exchange/subaccount
- **Hedge gap контроль**: мониторинг дисбаланса между парными позициями
- **Ликвидность**: проверка market impact перед входом
- **Концентрация**: ограничения на exposure в одной валютной паре

### 🔄 Reconciliation System
- **Автоматическая сверка**: позиции vs ожидаемое состояние
- **Детекция проблем**: "уплыли балансы/позиции"
- **Авто-исправление**: безопасное восстановление состояния
- **Аварийная остановка**: при критических расхождениях

### 📊 Margin Monitoring & ADL Protection
- **Безопасные уровни**: динамический расчёт максимального плеча
- **Мониторинг требований**: реакция на изменения margin requirements
- **ADL защита**: предотвращение принудительного закрытия
- **Автоснижение**: автоматическое уменьшение плеча при ухудшении условий

## Архитектура

```
FundingArbitrageStrategy
├── EdgeCalculator          # Расчёт и декомпозиция рентабельности
├── FundingScheduler        # Управление временными окнами
├── RiskManager            # Лимиты и контроль рисков
├── ReconciliationEngine   # Сверка и восстановление
├── MarginMonitor          # Мониторинг маржи и защита от ADL
└── PositionTracker        # Отслеживание ожидаемых состояний
```

## Использование

### Базовая настройка

```python
from hummingbot.strategy.funding_arbitrage import (
    FundingArbitrageStrategy, 
    FundingArbitrageConfig
)

# Конфигурация стратегии
config = FundingArbitrageConfig(
    min_edge_required=Decimal("0.0005"),      # 0.05% минимальная маржа
    max_notional_per_exchange=Decimal("50000"), # $50k лимит на биржу
    max_total_notional=Decimal("200000"),      # $200k общий лимит
    max_leverage=Decimal("5"),                 # Максимальное плечо 5x
    auto_leverage_reduction=True,              # Автоснижение плеча
    emergency_stop_on_critical_issues=True    # Аварийная остановка
)

# Инициализация стратегии
strategy = FundingArbitrageStrategy(
    exchanges=exchanges_dict,
    config=config,
    trading_pairs=['BTC-USDT', 'ETH-USDT']
)

# Запуск
strategy.start()
```

### Edge Decomposition

```python
from hummingbot.strategy.funding_arbitrage import EdgeCalculator

calculator = EdgeCalculator(min_edge_required=Decimal("0.0005"))

edge = calculator.calculate_edge(
    trading_pair='BTC-USDT',
    exchange_long='binance',
    exchange_short='bybit', 
    funding_rate_long=Decimal('0.0001'),
    funding_rate_short=Decimal('0.0015'),
    notional_amount=Decimal('10000'),
    fees_config=fees_config,
    borrow_rates=borrow_rates,
    slippage_estimates=slippage_estimates
)

# Просмотр декомпозиции
print("Edge Breakdown:")
for component, value in edge.to_display_dict().items():
    print(f"  {component}: {value}")

# Проверка прибыльности
if edge.is_profitable:
    print(f"✅ Profitable! Edge: {edge.total_edge}")
    print(f"   Margin over minimum: {edge.edge_margin}")
else:
    print(f"❌ Not profitable. Edge: {edge.total_edge}")
```

### Funding Scheduler

```python
from hummingbot.strategy.funding_arbitrage import FundingScheduler

scheduler = FundingScheduler()

# Проверка статуса settlement
status, minutes_left = scheduler.get_settlement_status(['binance', 'bybit'])
print(f"Settlement status: {status.value}")
print(f"Minutes until settlement: {minutes_left}")

# Можно ли открывать позицию?
can_open, reason = scheduler.should_open_position(
    exchanges=['binance', 'bybit'],
    minimum_time_horizon_minutes=30
)
print(f"Can open position: {can_open} ({reason})")

# Детальная информация по окнам
windows = scheduler.get_funding_window_info(['binance', 'bybit'])
for exchange, info in windows.items():
    print(f"{exchange}:")
    print(f"  Next settlement: {info['next_settlement_utc']}")
    print(f"  Close window starts: {info['close_window_starts']}")
```

### Risk Management

```python
from hummingbot.strategy.funding_arbitrage import RiskManager

risk_manager = RiskManager({
    'max_notional_per_exchange': '50000',
    'max_total_notional': '200000',
    'max_leverage': '5'
})

# Проверка лимитов перед входом
can_open, violations, risk_level = risk_manager.check_position_limits(
    exchange='binance',
    subaccount=None,
    trading_pair='BTC-USDT',
    proposed_notional=Decimal('10000'),
    proposed_leverage=Decimal('3')
)

print(f"Can open: {can_open}")
print(f"Risk level: {risk_level.value}")
if violations:
    print(f"Violations: {violations}")

# Проверка ликвидности
liquidity_ok, reason, impact = risk_manager.check_liquidity_risk(
    'binance', 'BTC-USDT', Decimal('10000')
)
print(f"Liquidity OK: {liquidity_ok} ({reason})")
print(f"Expected impact: {impact:.2%}")
```

### Margin Monitoring

```python
from hummingbot.strategy.funding_arbitrage import MarginMonitor

margin_monitor = MarginMonitor(
    max_allowed_leverage=Decimal('5'),
    auto_reduce_enabled=True
)

# Расчёт безопасного плеча
safe_leverage = margin_monitor.calculate_safe_leverage(
    exchange='binance',
    symbol='BTC-USDT',
    notional=Decimal('10000')
)
print(f"Safe leverage: {safe_leverage}")

# Нужно ли снизить плечо?
needs_reduction, new_leverage = margin_monitor.check_leverage_reduction_needed(
    position_id='pos_123'
)
if needs_reduction:
    print(f"Reduce leverage to: {new_leverage}")
```

## Конфигурация

### Основные параметры

```python
config = FundingArbitrageConfig(
    # Критерии входа
    min_edge_required=Decimal("0.0005"),           # Минимальная рентабельность
    min_funding_rate_diff=Decimal("0.0003"),       # Минимальная разница ставок
    min_position_hold_time_minutes=10,             # Минимальное время удержания
    
    # Управление рисками  
    max_notional_per_exchange=Decimal("50000"),    # Лимит на биржу
    max_total_notional=Decimal("200000"),          # Общий лимит
    max_leverage=Decimal("5"),                     # Максимальное плечо
    max_hedge_gap_percentage=Decimal("0.05"),      # Лимит hedge gap (5%)
    
    # Временные интервалы
    funding_check_interval_seconds=60,             # Проверка funding rates
    reconciliation_interval_seconds=300,           # Сверка позиций (5 мин)
    margin_check_interval_seconds=30,              # Проверка маржи
    
    # Безопасность
    emergency_stop_on_critical_issues=True,        # Аварийная остановка
    auto_leverage_reduction=True,                  # Автоснижение плеча
    auto_position_reconciliation=True              # Автосверка позиций
)
```

### Exchange-специфичные настройки

Система автоматически конфигурирует расписания funding settlement для поддерживаемых бирж:

- **Binance/Bybit/OKX**: 00:00, 08:00, 16:00 UTC (каждые 8 часов)
- **Gate.io/KuCoin**: 00:00, 08:00, 16:00 UTC
- **Настраиваемые буферы**: различные буферы времени перед settlement

## Мониторинг и метрики

### Статус стратегии

```python
status = strategy.get_strategy_status()

# Основные метрики
print(f"Active positions: {status['active_positions']}")
print(f"Total trades: {status['total_trades']}")
print(f"Funding collected: ${status['total_funding_collected']:.2f}")

# Risk summary
risk_summary = status['risk_summary']
print(f"Total notional: ${risk_summary['total_notional']:.2f}")
print(f"Hedge gaps: {risk_summary['hedge_gaps']}")

# Edge tracker
edge_stats = status['edge_tracker']
print(f"Profitability rate: {edge_stats['profitability_rate']:.1%}")
```

### Reconciliation метрики

```python
reconciliation = status['reconciliation']
print(f"Last check: {reconciliation['last_reconciliation_time']}")
print(f"Discrepancies: {reconciliation['last_total_discrepancies']}")
print(f"Emergency stop: {reconciliation['emergency_stop_active']}")
```

### Margin monitoring

```python
margin_status = status['margin_monitoring']
print(f"Monitoring active: {margin_status['monitoring_active']}")
print(f"Total accounts: {margin_status['total_accounts']}")
print(f"Margin status counts: {margin_status['margin_status_counts']}")
```

## Безопасность и Best Practices

### 🚨 Аварийные ситуации

1. **Emergency Stop**: Автоматически активируется при:
   - 3+ критических расхождениях в reconciliation
   - Критический уровень маржи
   - Системные ошибки

2. **Автоматические действия**:
   - Закрытие позиций при приближении к liquidation
   - Снижение плеча при ухудшении margin requirements
   - Остановка входов при недостаточной ликвидности

### 🛡️ Управление рисками

1. **Многоуровневые лимиты**:
   - Per-exchange limits
   - Per-subaccount limits
   - Total portfolio limits
   - Per-asset concentration limits

2. **Hedge gap мониторинг**:
   - Непрерывное отслеживание дисбаланса
   - Автоматические предупреждения
   - Принудительное закрытие при критических значениях

3. **Ликвидность**:
   - Проверка market impact перед входом
   - Адаптивные slippage буферы
   - Мониторинг order book depth

### 📊 Transparency

1. **Edge decomposition**: полная прозрачность каждого компонента прибыли
2. **Decision logging**: запись причин входа/отказа от позиций
3. **Risk attribution**: детализация рисков по источникам
4. **Performance analytics**: детальная аналитика эффективности

## Примеры использования

См. `examples/funding_arbitrage_example.py` для полного примера использования всех компонентов системы.

## Требования

- Python 3.8+
- Hummingbot framework
- AsyncIO support
- pytz для работы с часовыми поясами

## Лицензия

Следует лицензии основного проекта Hummingbot.