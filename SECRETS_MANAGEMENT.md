# Secrets Management Guide

This guide provides comprehensive instructions for securely managing secrets in the Hummingbot trading bot across different deployment environments.

## Table of Contents

1. [Overview](#overview)
2. [Secret Types](#secret-types)
3. [Docker Secrets Management](#docker-secrets-management)
4. [Kubernetes Secrets Management](#kubernetes-secrets-management)
5. [Environment Variables](#environment-variables)
6. [Best Practices](#best-practices)
7. [Secret Rotation](#secret-rotation)
8. [Auditing and Compliance](#auditing-and-compliance)

## Overview

Proper secrets management is critical for trading bot security. This system supports multiple secret management approaches:

- Docker Secrets (for Docker Swarm)
- Kubernetes Secrets (for Kubernetes deployments)
- SealedSecrets (for GitOps workflows)
- Environment Variables (for development and simple deployments)
- External Secret Management (HashiCorp Vault, AWS Secrets Manager, etc.)

## Secret Types

### Trading API Keys

These are the most critical secrets as they provide access to trading accounts:

```yaml
# Required trading secrets
secrets:
  # Binance
  - binance_api_key
  - binance_secret_key
  
  # Coinbase Pro
  - coinbase_api_key
  - coinbase_secret_key
  - coinbase_passphrase
  
  # Kraken
  - kraken_api_key
  - kraken_secret_key
  
  # Kucoin
  - kucoin_api_key
  - kucoin_secret_key
  - kucoin_passphrase
```

### Infrastructure Secrets

Database and service credentials:

```yaml
# Infrastructure secrets
secrets:
  # Database
  - postgres_user
  - postgres_password
  - postgres_db
  
  # Redis
  - redis_password
  
  # Gateway
  - gateway_passphrase
```

### Monitoring and Notification Secrets

For alerting and monitoring systems:

```yaml
# Monitoring secrets
secrets:
  # Telegram
  - telegram_token
  - telegram_chat_id
  
  # Slack
  - slack_webhook_url
  
  # Email
  - email_password
  - smtp_credentials
  
  # Monitoring services
  - prometheus_auth_token
  - grafana_api_key
  - datadog_api_key
```

## Docker Secrets Management

### Docker Swarm Secrets

For Docker Swarm deployments, use native Docker secrets:

#### Creating Secrets

```bash
# Create secrets from command line
echo "your_binance_api_key" | docker secret create binance_api_key -
echo "your_binance_secret" | docker secret create binance_secret_key -

# Create secrets from files
docker secret create postgres_password ./secrets/postgres_password.txt
docker secret create redis_password ./secrets/redis_password.txt

# Create multiple secrets from environment file
source .env.secrets
echo "$BINANCE_API_KEY" | docker secret create binance_api_key -
echo "$BINANCE_SECRET_KEY" | docker secret create binance_secret_key -
```

#### Using Secrets in Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  hummingbot:
    image: hummingbot/hummingbot:latest
    secrets:
      - binance_api_key
      - binance_secret_key
      - postgres_password
    environment:
      - BINANCE_API_KEY_FILE=/run/secrets/binance_api_key
      - BINANCE_SECRET_KEY_FILE=/run/secrets/binance_secret_key
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password

secrets:
  binance_api_key:
    external: true
  binance_secret_key:
    external: true
  postgres_password:
    external: true
```

### Docker Compose File Mounting

For development and single-node deployments:

```yaml
# docker-compose.yml
services:
  hummingbot:
    image: hummingbot/hummingbot:latest
    volumes:
      # Mount secrets directory (ensure proper permissions)
      - ./secrets:/run/secrets:ro
    environment:
      - BINANCE_API_KEY_FILE=/run/secrets/binance_api_key
      - BINANCE_SECRET_KEY_FILE=/run/secrets/binance_secret_key
```

#### Secrets Directory Structure

```
secrets/
├── trading/
│   ├── binance_api_key
│   ├── binance_secret_key
│   ├── coinbase_api_key
│   └── coinbase_secret_key
├── database/
│   ├── postgres_password
│   └── postgres_user
└── monitoring/
    ├── telegram_token
    └── slack_webhook_url
```

## Kubernetes Secrets Management

### Native Kubernetes Secrets

#### Creating Secrets

```bash
# Create secret from command line
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_api_key" \
  --from-literal=binance_secret_key="your_secret_key" \
  --namespace=hummingbot

# Create secret from files
kubectl create secret generic hummingbot-trading-keys \
  --from-file=binance_api_key=./secrets/binance_api_key \
  --from-file=binance_secret_key=./secrets/binance_secret_key \
  --namespace=hummingbot

# Create secret from YAML
kubectl apply -f k8s/secrets/hummingbot-trading-keys.yaml
```

#### Consuming Secrets in Deployments

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hummingbot
  namespace: hummingbot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: hummingbot
  template:
    metadata:
      labels:
        app: hummingbot
    spec:
      containers:
      - name: hummingbot
        image: hummingbot/hummingbot:latest
        env:
        # Environment variables from secrets
        - name: BINANCE_API_KEY
          valueFrom:
            secretKeyRef:
              name: hummingbot-trading-keys
              key: binance_api_key
        - name: BINANCE_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: hummingbot-trading-keys
              key: binance_secret_key
        volumeMounts:
        # Mount secrets as files
        - name: trading-secrets
          mountPath: /etc/secrets/trading
          readOnly: true
      volumes:
      - name: trading-secrets
        secret:
          secretName: hummingbot-trading-keys
```

### SealedSecrets (GitOps) and SOPS/age

SealedSecrets allow you to store encrypted secrets in Git repositories. As an alternative, SOPS + age can be used with a GitOps flow.

#### Installation

```bash
# Install SealedSecrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal client
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/kubeseal-0.24.0-linux-amd64.tar.gz
tar -xvzf kubeseal-0.24.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal

# Install SOPS and age
sudo apt-get update && sudo apt-get install -y gnupg
curl -sSL https://github.com/getsops/sops/releases/download/v3.8.1/sops-v3.8.1.linux.amd64 -o sops && sudo install -m 755 sops /usr/local/bin/sops
curl -sSL https://github.com/FiloSottile/age/releases/download/v1.1.1/age-v1.1.1-linux-amd64.tar.gz -o age.tar.gz && tar -xzf age.tar.gz && sudo install -m 755 age/age /usr/local/bin/age && sudo install -m 755 age/age-keygen /usr/local/bin/age-keygen
```

#### Creating SealedSecrets

```bash
# Create a regular secret and seal it
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_api_key" \
  --from-literal=binance_secret_key="your_secret_key" \
  --dry-run=client -o yaml | \
kubeseal -o yaml > k8s/sealed-secrets/hummingbot-trading-keys.yaml

# Apply the sealed secret
kubectl apply -f k8s/sealed-secrets/hummingbot-trading-keys.yaml

# Alternative: SOPS + age
age-keygen -o k8s/keys/age.txt
export SOPS_AGE_KEY_FILE=k8s/keys/age.txt
cat > k8s/secrets/hummingbot-trading-keys.yaml <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: hummingbot-trading-keys
  namespace: hummingbot
type: Opaque
stringData:
  binance_api_key: your_api_key
  binance_secret_key: your_secret_key
YAML
sops -e -i k8s/secrets/hummingbot-trading-keys.yaml
```

#### Example SealedSecret

```yaml
# sealed-trading-keys.yaml
apiVersion: bitnami.com/v1alpha1
kind: SealedSecret
metadata:
  name: hummingbot-trading-keys
  namespace: hummingbot
spec:
  encryptedData:
    binance_api_key: AgBy3i4OJSWK+PiTySYZZA9rO5QtVhDnJ8s...
    binance_secret_key: AgBy3i4OJSWK+PiTySYZZA9rO5QtVhDnJ8s...
  template:
    metadata:
      name: hummingbot-trading-keys
      namespace: hummingbot
    type: Opaque
```

### External Secret Operators

For integration with external secret management systems:

#### AWS Secrets Manager

```yaml
# external-secret.yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: hummingbot-trading-keys
  namespace: hummingbot
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secrets-manager
    kind: SecretStore
  target:
    name: hummingbot-trading-keys
    creationPolicy: Owner
  data:
  - secretKey: binance_api_key
    remoteRef:
      key: hummingbot/trading
      property: binance_api_key
  - secretKey: binance_secret_key
    remoteRef:
      key: hummingbot/trading
      property: binance_secret_key
```

## Environment Variables

For development and simple deployments:

### Environment File Management

```bash
# .env.secrets (never commit to git)
BINANCE_API_KEY="your_binance_api_key"
BINANCE_SECRET_KEY="your_binance_secret_key"
COINBASE_API_KEY="your_coinbase_api_key"
COINBASE_SECRET_KEY="your_coinbase_secret_key"
POSTGRES_PASSWORD="secure_database_password"
REDIS_PASSWORD="secure_redis_password"
TELEGRAM_TOKEN="your_telegram_bot_token"
```

### Loading Environment Variables

```bash
# Load from file
source .env.secrets

# Export for Docker Compose
export $(cat .env.secrets | xargs)

# Use with Docker Compose
docker-compose --env-file .env.secrets up
```

## Best Practices

- Principle of least privilege for API keys
- Separate secrets per environment (dev, staging, prod)
- Do not log secrets; scrub sensitive data from logs
- Enable audit logging for secret access
- Prefer SealedSecrets or SOPS/age for GitOps repositories
- Rotate keys regularly and automate rotation where possible
- Enforce RBAC and restrict who can read secrets

## Secret Rotation

1. Identify secret to rotate and scope of usage
2. Create new secret value in the secret manager (Kubernetes Secret/SealedSecret/SOPS)
3. Update dependent deployments with rolling restart
4. Validate application behavior post-rotation
5. Revoke old secret and remove residual access
6. Document rotation date and owner

## Auditing and Compliance

- Maintain an inventory of secrets and owners
- Review access policies regularly
- Enable Kubernetes audit logs and monitor secret access events
- Periodic security reviews and dependency scanning

This comprehensive secrets management strategy ensures secure handling of sensitive information across all deployment environments while maintaining operational efficiency and compliance requirements.