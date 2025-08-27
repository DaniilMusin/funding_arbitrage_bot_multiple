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

- **Docker Secrets** (for Docker Swarm)
- **Kubernetes Secrets** (for Kubernetes deployments)
- **SealedSecrets** (for GitOps workflows)
- **Environment Variables** (for development and simple deployments)
- **External Secret Management** (HashiCorp Vault, AWS Secrets Manager, etc.)

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
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: hummingbot-trading-keys
  namespace: hummingbot
type: Opaque
data:
  binance_api_key: $(echo -n "your_api_key" | base64)
  binance_secret_key: $(echo -n "your_secret_key" | base64)
EOF
```

#### Using Secrets in Pods

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hummingbot
spec:
  template:
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

### SealedSecrets (GitOps)

SealedSecrets allow you to store encrypted secrets in Git repositories:

#### Installation

```bash
# Install SealedSecrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/controller.yaml

# Install kubeseal client
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.0/kubeseal-0.24.0-linux-amd64.tar.gz
tar -xvzf kubeseal-0.24.0-linux-amd64.tar.gz
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
```

#### Creating SealedSecrets

```bash
# Create a regular secret and seal it
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_api_key" \
  --from-literal=binance_secret_key="your_secret_key" \
  --dry-run=client -o yaml | \
kubeseal -o yaml > sealed-trading-keys.yaml

# Apply the sealed secret
kubectl apply -f sealed-trading-keys.yaml
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

### Security Best Practices

1. **Never commit secrets to version control**
   ```bash
   # Add to .gitignore
   echo ".env.secrets" >> .gitignore
   echo "secrets/" >> .gitignore
   echo "*.key" >> .gitignore
   echo "*.pem" >> .gitignore
   ```

2. **Use least privilege access**
   - Grant minimal permissions required
   - Use read-only API keys when possible
   - Separate keys for different purposes

3. **Enable audit logging**
   ```yaml
   # Kubernetes audit policy
   apiVersion: audit.k8s.io/v1
   kind: Policy
   rules:
   - level: Metadata
     resources:
     - group: ""
       resources: ["secrets"]
   ```

4. **Encrypt secrets at rest**
   ```bash
   # Enable encryption at rest in Kubernetes
   kubectl create secret generic my-secret --from-literal=key=value
   ```

5. **Use separate secrets for different environments**
   - Development secrets should be different from production
   - Use environment-specific secret stores
   - Implement proper secret isolation

### Operational Best Practices

1. **Regular secret rotation**
   ```bash
   #!/bin/bash
   # Secret rotation script
   rotate_trading_keys() {
     # Generate new keys on exchange
     # Update secrets in secret store
     # Rolling restart of services
     kubectl rollout restart deployment/hummingbot
   }
   ```

2. **Secret validation**
   ```bash
   # Validate API keys before deployment
   validate_api_keys() {
     curl -H "X-MBX-APIKEY: $BINANCE_API_KEY" \
          "https://api.binance.com/api/v3/account"
   }
   ```

3. **Backup and recovery**
   ```bash
   # Backup secrets (encrypted)
   kubectl get secrets -o yaml > secrets-backup.yaml
   gpg --encrypt --recipient admin@company.com secrets-backup.yaml
   ```

### Development vs Production

#### Development Environment
- Use test/sandbox API keys
- Simple file-based secrets
- Relaxed security for convenience
- Clear text logging acceptable

#### Production Environment
- Use production API keys with minimal permissions
- Encrypted secret management system
- Strict access controls
- No clear text secrets in logs

## Secret Rotation

### Automated Rotation

```bash
#!/bin/bash
# automated-secret-rotation.sh

NAMESPACE="hummingbot"
SECRET_NAME="hummingbot-trading-keys"

# Function to rotate a specific API key
rotate_api_key() {
    local exchange=$1
    local api_key_name="${exchange}_api_key"
    local secret_key_name="${exchange}_secret_key"
    
    echo "Rotating $exchange API keys..."
    
    # Get new keys from exchange API (implement per exchange)
    # This is exchange-specific logic
    case $exchange in
        "binance")
            # Call Binance API to generate new keys
            # new_api_key=$(call_binance_api_for_new_key)
            # new_secret_key=$(call_binance_api_for_new_secret)
            ;;
        "coinbase")
            # Call Coinbase API to generate new keys
            ;;
    esac
    
    # Update Kubernetes secret
    kubectl patch secret $SECRET_NAME -n $NAMESPACE \
        --type='json' \
        -p="[{\"op\": \"replace\", \"path\": \"/data/$api_key_name\", \"value\":\"$(echo -n $new_api_key | base64)\"}]"
    
    kubectl patch secret $SECRET_NAME -n $NAMESPACE \
        --type='json' \
        -p="[{\"op\": \"replace\", \"path\": \"/data/$secret_key_name\", \"value\":\"$(echo -n $new_secret_key | base64)\"}]"
    
    # Rolling restart to pick up new secrets
    kubectl rollout restart deployment/hummingbot -n $NAMESPACE
    
    echo "$exchange API keys rotated successfully"
}

# Rotate all exchange keys
for exchange in binance coinbase kraken; do
    rotate_api_key $exchange
done
```

### Manual Rotation Process

1. **Generate new keys on exchange**
2. **Update secret store**
3. **Test new keys**
4. **Deploy updated secrets**
5. **Restart services**
6. **Verify operation**
7. **Revoke old keys**

## Auditing and Compliance

### Audit Logging

```yaml
# Kubernetes audit policy for secrets
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
# Log secret access at metadata level
- level: Metadata
  namespaces: ["hummingbot"]
  resources:
  - group: ""
    resources: ["secrets"]
  - group: "bitnami.com"
    resources: ["sealedsecrets"]

# Log secret modifications at request level
- level: Request
  namespaces: ["hummingbot"]
  resources:
  - group: ""
    resources: ["secrets"]
  verbs: ["create", "update", "patch", "delete"]
```

### Compliance Requirements

1. **Access Logging**
   - Log all secret access
   - Track who accessed what when
   - Maintain audit trail

2. **Encryption Standards**
   - Use strong encryption (AES-256)
   - Encrypt at rest and in transit
   - Regular key rotation

3. **Access Controls**
   - Role-based access control (RBAC)
   - Principle of least privilege
   - Regular access reviews

### Monitoring and Alerting

```yaml
# Prometheus alerting rules for secrets
groups:
- name: secrets.rules
  rules:
  - alert: SecretAccessAnomaly
    expr: increase(apiserver_audit_total{objectRef_resource="secrets"}[5m]) > 10
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "Unusual secret access pattern detected"
      
  - alert: SecretNotFound
    expr: kube_secret_info == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Required secret is missing"
```

## Troubleshooting

### Common Issues

1. **Secret not found**
   ```bash
   # Check if secret exists
   kubectl get secrets -n hummingbot
   kubectl describe secret hummingbot-trading-keys -n hummingbot
   ```

2. **Base64 encoding issues**
   ```bash
   # Correct way to encode secrets
   echo -n "your_secret" | base64
   # Decode to verify
   echo "encoded_secret" | base64 -d
   ```

3. **Permission issues**
   ```bash
   # Check RBAC permissions
   kubectl auth can-i get secrets --as=system:serviceaccount:hummingbot:default
   ```

4. **SealedSecret controller issues**
   ```bash
   # Check controller status
   kubectl get pods -n kube-system | grep sealed-secrets
   kubectl logs -n kube-system deployment/sealed-secrets-controller
   ```

### Debug Commands

```bash
# View secret contents (be careful in production)
kubectl get secret hummingbot-trading-keys -o yaml

# Test secret mounting
kubectl exec -it deployment/hummingbot -- cat /etc/secrets/trading/binance_api_key

# Check secret usage
kubectl describe pod <pod-name> | grep -A 5 -B 5 secret
```

## Migration and Backup

### Migrating Between Secret Systems

```bash
#!/bin/bash
# migrate-secrets.sh

# Export existing secrets
kubectl get secrets -n hummingbot -o yaml > current-secrets.yaml

# Transform to new format (implement transformation logic)
# ...

# Import to new system
kubectl apply -f new-secrets.yaml
```

### Backup Strategy

1. **Regular backups**
2. **Encrypted storage**
3. **Offsite backup copies**
4. **Recovery testing**
5. **Documentation**

This comprehensive secrets management strategy ensures secure handling of sensitive information across all deployment environments while maintaining operational efficiency and compliance requirements.