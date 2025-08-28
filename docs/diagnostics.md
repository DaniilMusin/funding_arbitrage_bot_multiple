## Диагностика

### hb-check

```bash
./hb-check connections --format=md --output-dir=./reports
./hb-check connections --format=json --output-dir=./reports
```

Артефакты сохраняются в `reports/YYYY-MM-DD/`.

### Health

Эндпоинты:
- /health/readiness
- /health/liveness
- /metrics

См. `README_EXCHANGE_CHECK.md` и `README.md`.
