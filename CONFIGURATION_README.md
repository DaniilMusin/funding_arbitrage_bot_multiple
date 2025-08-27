# Configuration, Secrets, and Environment Setup

This directory contains comprehensive configuration management for the Hummingbot trading bot with support for multiple deployment environments and secure secrets management.

## 🚀 Quick Start

### Docker Compose with Environment Profiles

```bash
# Local development
docker-compose --profile local up -d

# Paper trading
docker-compose --profile paper up -d

# Production (use with caution!)
docker-compose --profile prod up -d
```

### Automated Setup Script

```bash
# Setup local development environment
./scripts/environment-setup.sh -e local -t docker

# Setup paper trading with Kubernetes
./scripts/environment-setup.sh -e paper -t kubernetes

# Setup production (requires confirmation)
./scripts/environment-setup.sh -e prod -t docker
```

## 📁 File Structure

```
├── docker-compose.yml              # Multi-environment Docker Compose
├── .env.local                      # Local development config
├── .env.paper                      # Paper trading config  
├── .env.prod                       # Production config
├── k8s/
│   ├── helm/
│   │   └── values.yaml            # Helm chart with secrets mapping
│   ├── secrets-example.yaml       # Kubernetes secrets examples
│   └── sealed-secrets-example.yaml # SealedSecrets examples
├── scripts/
│   └── environment-setup.sh       # Automated setup script
├── ENVIRONMENT_SETUP.md           # Detailed setup guide
├── SECRETS_MANAGEMENT.md          # Comprehensive secrets guide
└── CONFIGURATION_README.md        # This file
```

## 🌍 Environment Profiles

### Local Development (`local`)
- **Purpose**: Development and testing
- **Trading**: Paper trading only
- **Security**: Relaxed for convenience
- **Monitoring**: Basic logging
- **Usage**: `docker-compose --profile local up`

### Paper Trading (`paper`)  
- **Purpose**: Strategy testing with realistic data
- **Trading**: Simulated trading
- **Security**: Standard security measures
- **Monitoring**: Full monitoring stack
- **Usage**: `docker-compose --profile paper up`

### Production (`prod`)
- **Purpose**: Live trading with real funds
- **Trading**: **REAL MONEY TRADING** ⚠️
- **Security**: Maximum security configuration
- **Monitoring**: Full monitoring + alerting
- **Usage**: `docker-compose --profile prod up`

## 🔐 Secrets Management

### Security Principles

✅ **DO:**
- Use environment-specific secret stores
- Rotate API keys regularly  
- Enable audit logging
- Use least-privilege access
- Encrypt secrets at rest

❌ **DON'T:**
- Commit secrets to version control
- Use production keys in development
- Share API keys between environments
- Log secrets in plain text

### Docker Secrets

```bash
# Create Docker secret
echo "your_api_key" | docker secret create binance_api_key -

# Use in docker-compose.yml
secrets:
  binance_api_key:
    external: true
```

### Kubernetes Secrets

```bash
# Create Kubernetes secret
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_key"

# Use SealedSecrets for GitOps
kubeseal -o yaml < secret.yaml > sealed-secret.yaml
```

### Environment Variables

```bash
# Set environment variables
export BINANCE_API_KEY="your_key"
export POSTGRES_PASSWORD="secure_password"

# Load from file
source .env.secrets
```

## ⚙️ Configuration Hierarchy

1. **Base configuration** (`.env`)
2. **Environment-specific** (`.env.local`, `.env.paper`, `.env.prod`)  
3. **Runtime environment variables** (highest priority)

## 🛠️ Setup Instructions

### Prerequisites

- Docker & Docker Compose
- kubectl (for Kubernetes)
- Helm (for Kubernetes)

### Step 1: Environment Files

```bash
# Copy examples and customize
cp .env.local.example .env.local
cp .env.paper.example .env.paper  
cp .env.prod.example .env.prod

# Edit with your configuration
nano .env.local
```

### Step 2: Set Secrets

**For Docker:**
```bash
# Set in environment file
echo "BINANCE_API_KEY=your_key" >> .env.local
```

**For Kubernetes:**
```bash
# Create secret
kubectl create secret generic hummingbot-trading-keys \
  --from-literal=binance_api_key="your_key"
```

### Step 3: Deploy

**Docker:**
```bash
docker-compose --profile paper up -d
```

**Kubernetes:**
```bash
helm install hummingbot-paper k8s/helm \
  --set global.environment=paper
```

## 📊 Monitoring

### Metrics (Paper/Prod only)
- **Prometheus**: http://localhost:9090
- **Health Check**: http://localhost:5723/livez

### Logs
```bash
# Docker
docker-compose --profile paper logs -f

# Kubernetes  
kubectl logs -f deployment/hummingbot
```

## 🚨 Production Safety

### Pre-deployment Checklist

- [ ] All secrets properly configured
- [ ] SSL/TLS enabled
- [ ] Rate limiting configured
- [ ] Monitoring and alerting set up
- [ ] Backup strategy implemented
- [ ] Risk limits configured
- [ ] Team notified of deployment

### Production Commands

```bash
# Deploy with confirmation
./scripts/environment-setup.sh -e prod -t docker

# Monitor deployment
docker-compose --profile prod logs -f hb-prod

# Emergency shutdown
docker-compose --profile prod down
```

## 🔧 Troubleshooting

### Common Issues

1. **Environment variables not loaded**
   ```bash
   docker-compose --profile local config
   ```

2. **Database connection failed**
   ```bash
   docker-compose logs postgres-local
   ```

3. **Secrets not found**
   ```bash
   kubectl get secrets
   kubectl describe secret hummingbot-trading-keys
   ```

### Debug Commands

```bash
# Check service status
docker-compose --profile paper ps

# Access container
docker-compose --profile paper exec hb-paper /bin/bash

# View configuration
docker-compose --profile paper config
```

## 📚 Documentation

- **[ENVIRONMENT_SETUP.md](ENVIRONMENT_SETUP.md)**: Detailed environment setup guide
- **[SECRETS_MANAGEMENT.md](SECRETS_MANAGEMENT.md)**: Comprehensive secrets management guide
- **[scripts/environment-setup.sh](scripts/environment-setup.sh)**: Automated setup script

## 🆘 Support

For issues and questions:

1. Check the troubleshooting section
2. Review the detailed documentation
3. Examine container/pod logs
4. Validate configuration files

## ⚖️ License & Disclaimer

This configuration setup is for educational and operational purposes. **Trading cryptocurrencies involves significant financial risk.** Always:

- Test thoroughly in paper trading mode
- Understand the risks before live trading
- Start with small amounts
- Monitor your positions actively
- Have proper risk management in place

**Never trade with funds you cannot afford to lose.**