## Запуск

Короткое руководство по запуску бота локально, в Docker Compose и Kubernetes (Helm). См. также `SETUP_INSTRUCTIONS.md` и `ENVIRONMENT_SETUP.md`.

### Быстрый старт

```bash
./install
./start
```

### Kubernetes (Helm)

```bash
helm upgrade --install hb k8s/helm -f k8s/helm/values-example.yaml
```
