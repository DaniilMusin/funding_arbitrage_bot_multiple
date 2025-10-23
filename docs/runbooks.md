## Runbooks

### Проблемы подключения к бирже
1. Запустить `./hb-check connections --format=md --output-dir=./reports`
2. Проверить ошибки и latency в отчете
3. Сопоставить с `exchange_connection_report.md`

### Повышенная задержка
1. `./hb-check latency -t 800`
2. Проверить маршрут сети и DNS

### Отказы pod'ов
1. Проверить readiness/liveness
2. Логи контейнера и события Kubernetes
