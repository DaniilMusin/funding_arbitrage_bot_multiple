# Environment Setup and Configuration Guide

This document provides comprehensive instructions for setting up and managing different environments (local, paper, production) for the Hummingbot trading bot.

## Table of Contents

1. [Environment Profiles](#environment-profiles)
2. [Docker Compose Setup](#docker-compose-setup)
3. [Kubernetes Deployment](#kubernetes-deployment)
4. [Secrets Management](#secrets-management)
5. [Configuration Files](#configuration-files)
6. [Security Best Practices](#security-best-practices)
7. [Monitoring and Observability](#monitoring-and-observability)

## Environment Profiles

The system supports three distinct environment profiles:

### Local Development (`local`)
- **Purpose**: Local development and testing
- **Trading**: Paper trading only
- **Security**: Relaxed for development convenience
- **Monitoring**: Minimal logging and telemetry
- **Database**: Local PostgreSQL with simple credentials
- **Redis**: No authentication

### Paper Trading (`paper`)
- **Purpose**: Strategy testing with simulated trading
- **Trading**: Paper trading with realistic market data
- **Security**: Standard security measures
- **Monitoring**: Full monitoring stack enabled
- **Database**: Dedicated database with authentication
- **Redis**: Password-protected

### Production (`prod`)
- **Purpose**: Live trading with real funds
- **Trading**: Live trading with maximum risk controls
- **Security**: Maximum security configuration
- **Monitoring**: Full monitoring, alerting, and logging
- **Database**: High-availability setup with connection pooling
- **Redis**: Full authentication and persistence

## Docker Compose Setup

### Prerequisites

1. Install Docker and Docker Compose
2. Clone the repository
3. Create environment-specific configuration files

### Basic Usage

```bash
# Start local development environment
docker-compose --profile local up -d

# Start paper trading environment
docker-compose --profile paper up -d

# Start production environment
docker-compose --profile prod up -d

# Start with monitoring stack
docker-compose --profile paper --profile monitoring up -d

# Start with gateway service
docker-compose --profile paper --profile gateway up -d
```

### Environment Files

Each environment uses specific configuration files:

- `.env` - Base configuration (shared across environments)
- `.env.local` - Local development overrides
- `.env.paper` - Paper trading configuration
- `.env.prod` - Production configuration

**IMPORTANT**: Never commit real secrets to version control. Use environment variables or secret management systems.

### Example Environment File Setup

```bash
# Copy example files
cp .env.local.example .env.local
cp .env.paper.example .env.paper
cp .env.prod.example .env.prod

# Edit with your specific configuration
nano .env.local
nano .env.paper
nano .env.prod
```

## Kubernetes Deployment

### Helm Chart Configuration

The Helm chart supports environment-specific deployments with proper secrets management.

#### Install with Helm

```bash
# Add your Helm repository (if needed)
helm repo add hummingbot ./k8s/helm

# Local environment
helm install hummingbot-local ./k8s/helm \
  -f k8s/helm/values.yaml \
  --set global.environment=local

# Paper trading environment
helm install hummingbot-paper ./k8s/helm \
  -f k8s/helm/values.yaml \
  --set global.environment=paper

# Production environment
helm install hummingbot-prod ./k8s/helm \
  -f k8s/helm/values.yaml \
  --set global.environment=prod
```

#### Environment-Specific Values

The Helm chart automatically applies environment-specific configurations based on the `global.environment` value.

## Secrets Management

### Docker Secrets (Docker Swarm)

For Docker Swarm deployments, use Docker secrets:

```bash
# Create secrets
echo "your_api_key" | docker secret create binance_api_key -
echo "your_secret_key" | docker secret create binance_secret_key -

# Reference in docker-compose.yml
secrets:
  binance_api_key:
    external: true
  binance_secret_key:
    external: true
```

### Kubernetes Secrets

For Kubernetes deployments, use native Kubernetes secrets or SealedSecrets:

```bash
# Create Kubernetes secret
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_api_key" \
  --from-literal=binance_secret_key="your_secret_key"

# Or use SealedSecrets for GitOps
kubeseal -o yaml < secret.yaml > sealed-secret.yaml
```

### Environment Variables for Secrets

Set secrets as environment variables (recommended for production):

```bash
# Set environment variables
export BINANCE_API_KEY="your_api_key"
export BINANCE_SECRET_KEY="your_secret_key"
export POSTGRES_PASSWORD="secure_password"
export REDIS_PASSWORD="redis_password"
```

## Configuration Files

### File Structure

```
.
├── .env                    # Base environment configuration
├── .env.local             # Local development overrides
├── .env.paper             # Paper trading configuration
├── .env.prod              # Production configuration
├── docker-compose.yml     # Multi-environment Docker Compose
└── k8s/
    ├── helm/
    │   └── values.yaml    # Helm chart values
    ├── secrets-example.yaml
    └── sealed-secrets-example.yaml
```

### Configuration Hierarchy

1. **Base configuration** (`.env`)
2. **Environment-specific overrides** (`.env.local`, `.env.paper`, `.env.prod`)
3. **Runtime environment variables** (highest priority)

### Key Configuration Parameters

#### Trading Configuration
- `PAPER_TRADING`: Enable/disable paper trading
- `TRADING_MODE`: Current trading mode
- `RISK_MANAGEMENT`: Risk management level

#### Database Configuration
- `POSTGRES_HOST`: Database host
- `POSTGRES_USER`: Database username
- `POSTGRES_PASSWORD`: Database password
- `POSTGRES_DB`: Database name

#### Security Configuration
- `ENABLE_SSL`: Enable SSL/TLS
- `RATE_LIMIT_ENABLED`: Enable API rate limiting
- `API_TIMEOUT`: API request timeout

## Security Best Practices

### Secret Management

1. **Never commit secrets to version control**
2. **Use environment-specific secret stores**
3. **Rotate API keys regularly**
4. **Use least-privilege access principles**
5. **Enable audit logging for secret access**

### Production Security Checklist

- [ ] All secrets stored in secure secret management system
- [ ] SSL/TLS enabled for all communications
- [ ] Rate limiting configured
- [ ] IP whitelisting enabled (if applicable)
- [ ] 2FA enabled for critical accounts
- [ ] Regular security audits scheduled
- [ ] Backup encryption enabled
- [ ] Network policies configured
- [ ] Container security scanning enabled

### Network Security

```yaml
# Example network policy for Kubernetes
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: hummingbot-network-policy
spec:
  podSelector:
    matchLabels:
      app: hummingbot
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: monitoring
    ports:
    - protocol: TCP
      port: 5723
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 443  # HTTPS
    - protocol: TCP
      port: 80   # HTTP
```

## Monitoring and Observability

### Prometheus Metrics

The application exposes metrics on port 9090:

- Trading performance metrics
- System resource usage
- API response times
- Error rates

### Grafana Dashboards

Pre-configured dashboards available for:

- Trading performance
- System health
- Exchange connectivity
- Risk metrics

### Alerting

Configure alerts for:

- Trading losses exceeding thresholds
- System errors
- Exchange connectivity issues
- Resource exhaustion

### Log Management

Each environment has different logging configurations:

#### Local Development
- Log level: DEBUG
- File size: 100MB
- Retention: 7 days

#### Paper Trading
- Log level: INFO
- File size: 50MB
- Retention: 14 days

#### Production
- Log level: WARN
- File size: 20MB
- Retention: 90 days
- Log shipping enabled

## Troubleshooting

### Common Issues

1. **Environment variables not loaded**
   ```bash
   # Check if environment file exists
   ls -la .env*
   
   # Verify environment variables
   docker-compose config
   ```

2. **Database connection issues**
   ```bash
   # Check database logs
   docker-compose logs postgres-<env>
   
   # Test connection
   docker-compose exec hb-<env> pg_isready -h postgres-<env>
   ```

3. **Secret mounting issues**
   ```bash
   # Verify secrets are created
   kubectl get secrets
   
   # Check secret mounting
   kubectl describe pod <pod-name>
   ```

### Debugging Commands

```bash
# View current configuration
docker-compose config

# Check service status
docker-compose ps

# View logs
docker-compose logs hb-<env>

# Execute shell in container
docker-compose exec hb-<env> /bin/bash

# Validate Kubernetes deployment
kubectl get pods
kubectl describe deployment hummingbot
kubectl logs deployment/hummingbot
```

## Migration Guide

### From Single Environment to Multi-Environment

1. **Backup current configuration**
   ```bash
   cp docker-compose.yml docker-compose.yml.backup
   cp .env .env.backup
   ```

2. **Update docker-compose.yml** with profile support

3. **Create environment-specific files**
   ```bash
   cp .env .env.local
   cp .env .env.paper
   cp .env .env.prod
   ```

4. **Update each environment file** with appropriate settings

5. **Test each environment**
   ```bash
   docker-compose --profile local config
   docker-compose --profile paper config
   docker-compose --profile prod config
   ```

### Kubernetes Migration

1. **Install SealedSecrets controller** (if using SealedSecrets)
2. **Create secrets** using provided templates
3. **Deploy Helm chart** with appropriate values
4. **Verify deployment** and monitor logs

## Support and Resources

- [Hummingbot Documentation](https://docs.hummingbot.org/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Helm Documentation](https://helm.sh/docs/)
- [SealedSecrets Documentation](https://sealed-secrets.netlify.app/)