#!/bin/bash

# ======================================
# Ingestify Smart Startup Script
# Auto-detects shared infrastructure
# ======================================

set -e  # Exit on error

PROJECT_NAME="ingestify"
SHARED_REDIS="shared-redis"
SHARED_MINIO="shared-minio"
SHARED_ELASTICSEARCH="shared-elasticsearch"
SHARED_NETWORK="shared-dev-network"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Enable BuildKit for better caching and faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# JWT secret: reuse the one already in .env (so existing sessions stay valid) or generate one
JWT_SECRET_KEY="${JWT_SECRET_KEY:-$(grep -s '^JWT_SECRET_KEY=' .env | cut -d= -f2- || true)}"
if [ -z "$JWT_SECRET_KEY" ]; then
    JWT_SECRET_KEY="$(openssl rand -hex 32)"
    echo -e "${YELLOW}🔑 Generated a new JWT_SECRET_KEY (saved to .env)${NC}"
fi

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Ingestify - Smart Startup${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# Function to check if a container is running
is_container_running() {
    docker ps --format '{{.Names}}' | grep -q "^$1$"
}

# Function to check if a network exists
network_exists() {
    docker network ls --format '{{.Name}}' | grep -q "^$1$"
}

# Function to create shared infrastructure network if needed
ensure_shared_network() {
    if ! network_exists "$SHARED_NETWORK"; then
        echo -e "${YELLOW}🔗 Creating shared network: $SHARED_NETWORK${NC}"
        docker network create "$SHARED_NETWORK" 2>/dev/null || true
    fi
}

# Function to connect project to shared infrastructure
connect_to_shared_infra() {
    local redis_host="host.docker.internal"
    local minio_host="host.docker.internal"
    local es_host="host.docker.internal"

    # If shared network exists, use container names
    if network_exists "$SHARED_NETWORK"; then
        redis_host="$SHARED_REDIS"
        minio_host="$SHARED_MINIO"
        es_host="$SHARED_ELASTICSEARCH"
    fi

    export REDIS_HOST="$redis_host"
    export MINIO_HOST="$minio_host"
    export ELASTICSEARCH_HOST="$es_host"

    echo -e "${GREEN}✅ Using shared infrastructure:${NC}"
    echo -e "   Redis: ${CYAN}$REDIS_HOST${NC}"
    echo -e "   MinIO: ${CYAN}$MINIO_HOST${NC}"
    echo -e "   Elasticsearch: ${CYAN}$ES_HOST${NC}"
}

# Check if shared infrastructure is running
echo -e "${CYAN}🔍 Detecting infrastructure...${NC}"
echo ""

SHARED_INFRA_RUNNING=false
if is_container_running "$SHARED_REDIS" && \
   is_container_running "$SHARED_MINIO" && \
   is_container_running "$SHARED_ELASTICSEARCH"; then
    SHARED_INFRA_RUNNING=true
    echo -e "${GREEN}✅ Shared infrastructure detected and running${NC}"
    connect_to_shared_infra

    # Ensure shared network exists and connect to it
    ensure_shared_network

    # Create .env file with shared infra settings
    cat > .env << EOF
JWT_SECRET_KEY=$JWT_SECRET_KEY
REDIS_HOST=$REDIS_HOST
MINIO_HOST=$MINIO_HOST
ELASTICSEARCH_HOST=$ELASTICSEARCH_HOST
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
EOF

    # Connect ingestify network to shared network if not already connected
    if network_exists "ingestify-network" && network_exists "$SHARED_NETWORK"; then
        # Create a bridge container to connect networks (Docker doesn't support direct network connection)
        echo -e "${YELLOW}🔗 Connecting to shared network...${NC}"
    fi

    echo ""
    echo -e "${CYAN}📦 Starting application services only...${NC}"
    docker compose up -d --build api worker beat frontend
else
    echo -e "${YELLOW}⚠️  Shared infrastructure not found${NC}"
    echo -e "${CYAN}📦 Starting with local infrastructure...${NC}"
    echo ""

    # Reset .env to defaults, keeping only the JWT secret
    echo "JWT_SECRET_KEY=$JWT_SECRET_KEY" > .env

    # Start everything including local infrastructure
    docker compose --profile infra up -d --build

    echo ""
    echo -e "${BLUE}💡 Tip: Start shared infrastructure once for all projects:${NC}"
    echo -e "   ${CYAN}docker compose -f docker-compose.infra.yml up -d${NC}"
fi

echo ""
echo -e "${CYAN}⏳ Waiting for services to be ready...${NC}"
sleep 8

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  Service Status${NC}"
echo -e "${BLUE}======================================${NC}"
docker compose ps

# Initialize MinIO buckets if needed
echo ""
echo -e "${CYAN}🪣 Ensuring MinIO buckets exist...${NC}"

MINIO_CONTAINER=""
if is_container_running "$SHARED_MINIO"; then
    MINIO_CONTAINER="$SHARED_MINIO"
elif is_container_running "ingestify-minio"; then
    MINIO_CONTAINER="ingestify-minio"
fi

if [ -n "$MINIO_CONTAINER" ]; then
    # Wait for MinIO to be ready
    sleep 2

    # Create buckets
    docker exec $MINIO_CONTAINER sh -c "
        mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
        mc mb local/ingestify-uploads 2>/dev/null || true
        mc mb local/ingestify-pages 2>/dev/null || true
        mc mb local/ingestify-audio 2>/dev/null || true
        mc mb local/ingestify-results 2>/dev/null || true
    " 2>/dev/null || echo -e "${YELLOW}⚠️  MinIO not ready yet, buckets will be created on first use${NC}"
fi

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  API Health Check${NC}"
echo -e "${BLUE}======================================${NC}"
sleep 2
curl -s http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo -e "${YELLOW}API starting up...${NC}"

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  ✅ Ingestify is Ready!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "${CYAN}Access Points:${NC}"
echo -e "  🌐 Frontend:     ${GREEN}http://localhost:3000${NC}"
echo -e "  🔌 API:          ${GREEN}http://localhost:8000${NC}"
echo -e "  📚 API Docs:     ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  ❤️  Health:       ${GREEN}http://localhost:8000/health${NC}"

if [ "$SHARED_INFRA_RUNNING" = false ]; then
    echo ""
    echo -e "${CYAN}Infrastructure:${NC}"
    echo -e "  📦 MinIO UI:     ${GREEN}http://localhost:9001${NC} ${YELLOW}(minioadmin / minioadmin)${NC}"
    echo -e "  🔍 Elasticsearch: ${GREEN}http://localhost:9200${NC}"
    echo -e "  📮 Redis:        ${GREEN}localhost:6379${NC}"
fi

echo ""
echo -e "${CYAN}Useful Commands:${NC}"
echo -e "  📋 View logs:    ${YELLOW}docker compose logs -f${NC}"
echo -e "  🛑 Stop:         ${YELLOW}docker compose down${NC}"
echo -e "  🔄 Restart:      ${YELLOW}./start.sh${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""
