#!/bin/bash

# Environment Setup Script for Hummingbot
# This script helps set up different environment profiles

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT=""
SETUP_TYPE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Hummingbot Environment Setup Script  ${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

show_help() {
    cat << EOF
Usage: $0 [OPTIONS]

Setup script for Hummingbot environment configuration.

OPTIONS:
    -e, --environment ENV    Environment type (local, paper, prod)
    -t, --type TYPE         Setup type (docker, kubernetes)
    -h, --help             Show this help message

EXAMPLES:
    $0 -e local -t docker
    $0 --environment paper --type kubernetes
    $0 -e prod -t docker

ENVIRONMENTS:
    local       Local development environment
    paper       Paper trading environment  
    prod        Production environment

SETUP TYPES:
    docker      Docker Compose setup
    kubernetes  Kubernetes/Helm setup
EOF
}

check_dependencies() {
    print_info "Checking dependencies..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_success "Docker found"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_success "Docker Compose found"
    
    if [[ "$SETUP_TYPE" == "kubernetes" ]]; then
        # Check kubectl
        if ! command -v kubectl &> /dev/null; then
            print_error "kubectl is not installed. Please install kubectl first."
            exit 1
        fi
        print_success "kubectl found"
        
        # Check helm
        if ! command -v helm &> /dev/null; then
            print_error "Helm is not installed. Please install Helm first."
            exit 1
        fi
        print_success "Helm found"
    fi
}

setup_environment_files() {
    print_info "Setting up environment files for $ENVIRONMENT environment..."
    
    cd "$PROJECT_ROOT"
    
    # Create base .env if it doesn't exist
    if [[ ! -f .env ]]; then
        print_warning ".env file not found, creating template..."
        cat > .env << 'EOF'
# Base Hummingbot Configuration
# This file contains shared configuration across all environments

# Application
APP_NAME=hummingbot
VERSION=latest

# Network
HEALTH_PORT=5723

# Logging
LOG_DIR=./logs
DATA_DIR=./data
CONF_DIR=./conf

# Gateway (uncomment if using)
# GATEWAY_PASSPHRASE=your_gateway_passphrase
EOF
        print_success "Created base .env file"
    fi
    
    # Check if environment-specific file exists
    ENV_FILE=".env.$ENVIRONMENT"
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error "Environment file $ENV_FILE not found!"
        print_info "Please create $ENV_FILE with appropriate configuration."
        exit 1
    fi
    print_success "Environment file $ENV_FILE found"
    
    # Validate environment file
    print_info "Validating environment configuration..."
    
    case $ENVIRONMENT in
        "local")
            if ! grep -q "PAPER_TRADING=true" "$ENV_FILE"; then
                print_warning "Local environment should have PAPER_TRADING=true"
            fi
            ;;
        "paper")
            if ! grep -q "PAPER_TRADING=true" "$ENV_FILE"; then
                print_warning "Paper environment should have PAPER_TRADING=true"
            fi
            ;;
        "prod")
            if grep -q "PAPER_TRADING=true" "$ENV_FILE"; then
                print_error "Production environment should have PAPER_TRADING=false"
                print_error "Please review your production configuration!"
                exit 1
            fi
            ;;
    esac
}

validate_secrets() {
    print_info "Validating secrets configuration..."
    
    case $ENVIRONMENT in
        "local")
            print_info "Local environment - secrets validation skipped"
            ;;
        "paper"|"prod")
            # Check for required secret environment variables
            required_vars=("POSTGRES_PASSWORD" "REDIS_PASSWORD")
            
            for var in "${required_vars[@]}"; do
                if [[ -z "${!var}" ]]; then
                    print_warning "$var is not set. Make sure to set it before deployment."
                fi
            done
            
            # Check for trading API keys (warn if missing)
            trading_vars=("BINANCE_API_KEY" "BINANCE_SECRET_KEY")
            for var in "${trading_vars[@]}"; do
                if [[ -z "${!var}" ]]; then
                    print_warning "$var is not set. Set trading API keys for live trading."
                fi
            done
            ;;
    esac
}

setup_docker() {
    print_info "Setting up Docker environment for $ENVIRONMENT..."
    
    cd "$PROJECT_ROOT"
    
    # Validate docker-compose.yml
    if [[ ! -f docker-compose.yml ]]; then
        print_error "docker-compose.yml not found!"
        exit 1
    fi
    
    # Check if profile exists
    if ! grep -q "profiles:.*$ENVIRONMENT" docker-compose.yml; then
        print_error "Profile '$ENVIRONMENT' not found in docker-compose.yml"
        exit 1
    fi
    print_success "Docker Compose profile '$ENVIRONMENT' found"
    
    # Validate configuration
    print_info "Validating Docker Compose configuration..."
    if ! docker-compose --profile "$ENVIRONMENT" config > /dev/null; then
        print_error "Docker Compose configuration validation failed!"
        exit 1
    fi
    print_success "Docker Compose configuration is valid"
    
    # Create directories
    print_info "Creating required directories..."
    directories=("logs" "data" "conf" "certs" "gateway_files")
    for dir in "${directories[@]}"; do
        if [[ ! -d "$dir" ]]; then
            mkdir -p "$dir"
            print_success "Created directory: $dir"
        fi
    done
    
    # Set permissions
    print_info "Setting directory permissions..."
    chmod 755 logs data conf certs 2>/dev/null || true
    
    # Pull images
    print_info "Pulling Docker images..."
    docker-compose --profile "$ENVIRONMENT" pull
    print_success "Docker images pulled successfully"
}

setup_kubernetes() {
    print_info "Setting up Kubernetes environment for $ENVIRONMENT..."
    
    cd "$PROJECT_ROOT"
    
    # Check if Kubernetes cluster is accessible
    if ! kubectl cluster-info > /dev/null 2>&1; then
        print_error "Cannot access Kubernetes cluster. Please check your kubeconfig."
        exit 1
    fi
    print_success "Kubernetes cluster is accessible"
    
    # Create namespace if it doesn't exist
    NAMESPACE="hummingbot"
    if ! kubectl get namespace "$NAMESPACE" > /dev/null 2>&1; then
        print_info "Creating namespace: $NAMESPACE"
        kubectl create namespace "$NAMESPACE"
        print_success "Namespace created: $NAMESPACE"
    else
        print_success "Namespace exists: $NAMESPACE"
    fi
    
    # Check Helm chart
    HELM_CHART_DIR="k8s/helm"
    if [[ ! -d "$HELM_CHART_DIR" ]]; then
        print_error "Helm chart directory not found: $HELM_CHART_DIR"
        exit 1
    fi
    
    # Validate Helm chart
    print_info "Validating Helm chart..."
    if ! helm lint "$HELM_CHART_DIR" > /dev/null; then
        print_error "Helm chart validation failed!"
        exit 1
    fi
    print_success "Helm chart is valid"
    
    # Check for secrets
    print_info "Checking for required secrets..."
    required_secrets=("hummingbot-trading-keys" "hummingbot-db-credentials")
    
    for secret in "${required_secrets[@]}"; do
        if ! kubectl get secret "$secret" -n "$NAMESPACE" > /dev/null 2>&1; then
            print_warning "Secret '$secret' not found. You'll need to create it before deployment."
            print_info "See k8s/secrets-example.yaml for examples"
        else
            print_success "Secret found: $secret"
        fi
    done
}

deploy_environment() {
    print_info "Deploying $ENVIRONMENT environment using $SETUP_TYPE..."
    
    case $SETUP_TYPE in
        "docker")
            cd "$PROJECT_ROOT"
            print_info "Starting services with Docker Compose..."
            docker-compose --profile "$ENVIRONMENT" up -d
            
            # Wait for services to be ready
            print_info "Waiting for services to be ready..."
            sleep 10
            
            # Check service status
            docker-compose --profile "$ENVIRONMENT" ps
            print_success "Docker Compose deployment completed"
            ;;
            
        "kubernetes")
            cd "$PROJECT_ROOT"
            RELEASE_NAME="hummingbot-$ENVIRONMENT"
            
            print_info "Deploying with Helm..."
            helm upgrade --install "$RELEASE_NAME" k8s/helm \
                --namespace hummingbot \
                --set global.environment="$ENVIRONMENT" \
                --wait --timeout=300s
            
            print_success "Kubernetes deployment completed"
            
            # Show deployment status
            kubectl get pods -n hummingbot
            ;;
    esac
}

verify_deployment() {
    print_info "Verifying deployment..."
    
    case $SETUP_TYPE in
        "docker")
            # Check if main service is running
            if docker-compose --profile "$ENVIRONMENT" ps | grep -q "Up"; then
                print_success "Services are running"
                
                # Test health endpoint if available
                if [[ "$ENVIRONMENT" != "local" ]]; then
                    sleep 5
                    if curl -f http://localhost:5723/livez > /dev/null 2>&1; then
                        print_success "Health check passed"
                    else
                        print_warning "Health check failed or not available"
                    fi
                fi
            else
                print_error "Some services are not running properly"
                return 1
            fi
            ;;
            
        "kubernetes")
            # Check pod status
            RELEASE_NAME="hummingbot-$ENVIRONMENT"
            if kubectl get pods -n hummingbot -l app.kubernetes.io/instance="$RELEASE_NAME" | grep -q "Running"; then
                print_success "Pods are running"
            else
                print_warning "Some pods may not be ready yet"
                kubectl get pods -n hummingbot
            fi
            ;;
    esac
}

show_next_steps() {
    print_info "Deployment completed! Next steps:"
    echo
    
    case $SETUP_TYPE in
        "docker")
            echo "View logs:"
            echo "  docker-compose --profile $ENVIRONMENT logs -f"
            echo
            echo "Stop services:"
            echo "  docker-compose --profile $ENVIRONMENT down"
            echo
            echo "Access container:"
            echo "  docker-compose --profile $ENVIRONMENT exec hb-$ENVIRONMENT /bin/bash"
            ;;
            
        "kubernetes")
            echo "View logs:"
            echo "  kubectl logs -n hummingbot -l app=hummingbot -f"
            echo
            echo "Get pod status:"
            echo "  kubectl get pods -n hummingbot"
            echo
            echo "Access pod:"
            echo "  kubectl exec -n hummingbot -it deployment/hummingbot -- /bin/bash"
            ;;
    esac
    
    echo
    case $ENVIRONMENT in
        "local")
            echo "Local development environment is ready!"
            echo "You can now develop and test your strategies."
            ;;
        "paper")
            echo "Paper trading environment is ready!"
            echo "Configure your strategies and start paper trading."
            ;;
        "prod")
            echo "Production environment is ready!"
            echo "⚠️  WARNING: This is a PRODUCTION environment with real trading."
            echo "⚠️  Ensure all configurations are correct before enabling live trading."
            ;;
    esac
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -t|--type)
            SETUP_TYPE="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate arguments
if [[ -z "$ENVIRONMENT" ]]; then
    print_error "Environment is required. Use -e or --environment"
    show_help
    exit 1
fi

if [[ -z "$SETUP_TYPE" ]]; then
    print_error "Setup type is required. Use -t or --type"
    show_help
    exit 1
fi

# Validate environment
case $ENVIRONMENT in
    "local"|"paper"|"prod")
        ;;
    *)
        print_error "Invalid environment: $ENVIRONMENT"
        print_error "Valid environments: local, paper, prod"
        exit 1
        ;;
esac

# Validate setup type
case $SETUP_TYPE in
    "docker"|"kubernetes")
        ;;
    *)
        print_error "Invalid setup type: $SETUP_TYPE"
        print_error "Valid setup types: docker, kubernetes"
        exit 1
        ;;
esac

# Main execution
main() {
    print_header
    
    print_info "Setting up $ENVIRONMENT environment using $SETUP_TYPE"
    echo
    
    check_dependencies
    setup_environment_files
    validate_secrets
    
    case $SETUP_TYPE in
        "docker")
            setup_docker
            ;;
        "kubernetes")
            setup_kubernetes
            ;;
    esac
    
    # Ask for confirmation before deployment
    if [[ "$ENVIRONMENT" == "prod" ]]; then
        echo
        print_warning "You are about to deploy to PRODUCTION environment!"
        print_warning "This will involve REAL TRADING with REAL MONEY!"
        echo
        read -p "Are you sure you want to continue? (yes/no): " confirm
        if [[ "$confirm" != "yes" ]]; then
            print_info "Deployment cancelled."
            exit 0
        fi
    fi
    
    deploy_environment
    verify_deployment
    show_next_steps
    
    print_success "Environment setup completed successfully!"
}

# Run main function
main