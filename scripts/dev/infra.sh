#!/bin/bash

cd "$(dirname "$0")/../.."  # scripts/dev/ -> project root

# ======================================
# Shared Infrastructure Manager
# Quick commands for shared infra
# ======================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

SHARED_REDIS="shared-redis"
SHARED_MINIO="shared-minio"
SHARED_ELASTICSEARCH="shared-elasticsearch"

# Function to check if a container is running
is_running() {
    docker ps --format '{{.Names}}' | grep -q "^$1$"
}

# Function to show status
show_status() {
    echo ""
    echo -e "${CYAN}Shared Infrastructure Status:${NC}"
    echo ""

    if is_running "$SHARED_REDIS"; then
        echo -e "  Redis:         ${GREEN}✅ Running${NC}"
    else
        echo -e "  Redis:         ${RED}❌ Stopped${NC}"
    fi

    if is_running "$SHARED_MINIO"; then
        echo -e "  MinIO:         ${GREEN}✅ Running${NC}"
    else
        echo -e "  MinIO:         ${RED}❌ Stopped${NC}"
    fi

    if is_running "$SHARED_ELASTICSEARCH"; then
        echo -e "  Elasticsearch: ${GREEN}✅ Running${NC}"
    else
        echo -e "  Elasticsearch: ${RED}❌ Stopped${NC}"
    fi

    echo ""

    if is_running "$SHARED_REDIS" && is_running "$SHARED_MINIO" && is_running "$SHARED_ELASTICSEARCH"; then
        echo -e "${GREEN}All infrastructure services are running!${NC}"
        echo ""
        echo -e "${CYAN}Access URLs:${NC}"
        echo -e "  Redis:         localhost:6379"
        echo -e "  MinIO API:     http://localhost:9000"
        echo -e "  MinIO UI:      http://localhost:9001 (credentials: MINIO_ROOT_USER / MINIO_ROOT_PASSWORD in .env)"
        echo -e "  Elasticsearch: http://localhost:9200"
    fi

    echo ""
}

# Function to start infrastructure
start_infra() {
    echo -e "${CYAN}🚀 Starting shared infrastructure...${NC}"
    echo ""

    docker compose -f docker-compose.infra.yml up -d

    echo ""
    echo -e "${GREEN}✅ Shared infrastructure started!${NC}"

    # Wait a bit and show status
    sleep 3
    show_status
}

# Function to stop infrastructure
stop_infra() {
    echo -e "${YELLOW}🛑 Stopping shared infrastructure...${NC}"
    echo ""

    docker compose -f docker-compose.infra.yml down

    echo ""
    echo -e "${GREEN}✅ Shared infrastructure stopped!${NC}"
    echo ""
}

# Function to restart infrastructure
restart_infra() {
    echo -e "${CYAN}🔄 Restarting shared infrastructure...${NC}"
    echo ""

    stop_infra
    sleep 2
    start_infra
}

# Function to view logs
view_logs() {
    echo -e "${CYAN}📋 Viewing infrastructure logs (Ctrl+C to stop)...${NC}"
    echo ""

    docker compose -f docker-compose.infra.yml logs -f
}

# Function to show help
show_help() {
    echo ""
    echo -e "${BLUE}Shared Infrastructure Manager${NC}"
    echo ""
    echo -e "${CYAN}Usage:${NC}"
    echo -e "  ./scripts/dev/infra.sh ${GREEN}start${NC}      - Start shared infrastructure"
    echo -e "  ./scripts/dev/infra.sh ${YELLOW}stop${NC}       - Stop shared infrastructure"
    echo -e "  ./scripts/dev/infra.sh ${CYAN}restart${NC}    - Restart infrastructure"
    echo -e "  ./scripts/dev/infra.sh ${BLUE}status${NC}     - Show status"
    echo -e "  ./scripts/dev/infra.sh ${CYAN}logs${NC}       - View logs"
    echo -e "  ./scripts/dev/infra.sh ${GREEN}test${NC}       - Test connectivity"
    echo -e "  ./scripts/dev/infra.sh ${RED}clean${NC}      - Remove all data (WARNING)"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo -e "  ./scripts/dev/infra.sh start"
    echo -e "  ./scripts/dev/infra.sh status"
    echo ""
}

# Function to test connectivity
test_connectivity() {
    echo ""
    echo -e "${CYAN}🔍 Testing infrastructure connectivity...${NC}"
    echo ""

    # Test Redis
    if is_running "$SHARED_REDIS"; then
        echo -n "  Redis:         "
        if docker exec $SHARED_REDIS redis-cli ping >/dev/null 2>&1; then
            echo -e "${GREEN}✅ OK${NC}"
        else
            echo -e "${RED}❌ FAILED${NC}"
        fi
    else
        echo -e "  Redis:         ${YELLOW}⚠️  Not running${NC}"
    fi

    # Test MinIO
    if is_running "$SHARED_MINIO"; then
        echo -n "  MinIO:         "
        if curl -sf http://localhost:9000/minio/health/live >/dev/null 2>&1; then
            echo -e "${GREEN}✅ OK${NC}"
        else
            echo -e "${RED}❌ FAILED${NC}"
        fi
    else
        echo -e "  MinIO:         ${YELLOW}⚠️  Not running${NC}"
    fi

    # Test Elasticsearch
    if is_running "$SHARED_ELASTICSEARCH"; then
        echo -n "  Elasticsearch: "
        if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
            echo -e "${GREEN}✅ OK${NC}"
        else
            echo -e "${RED}❌ FAILED${NC}"
        fi
    else
        echo -e "  Elasticsearch: ${YELLOW}⚠️  Not running${NC}"
    fi

    echo ""
}

# Function to clean all data
clean_data() {
    echo ""
    echo -e "${RED}⚠️  WARNING: This will remove ALL shared infrastructure data!${NC}"
    echo -e "${RED}   This includes:${NC}"
    echo -e "${RED}   - All Redis data${NC}"
    echo -e "${RED}   - All MinIO buckets and files${NC}"
    echo -e "${RED}   - All Elasticsearch indices${NC}"
    echo ""
    echo -n "Are you sure? Type 'yes' to confirm: "
    read confirmation

    if [ "$confirmation" = "yes" ]; then
        echo ""
        echo -e "${YELLOW}🧹 Removing all infrastructure data...${NC}"
        docker compose -f docker-compose.infra.yml down -v
        echo ""
        echo -e "${GREEN}✅ Cleanup complete!${NC}"
        echo ""
    else
        echo ""
        echo -e "${CYAN}Cleanup cancelled.${NC}"
        echo ""
    fi
}

# Main script
case "${1:-help}" in
    start)
        start_infra
        ;;
    stop)
        stop_infra
        ;;
    restart)
        restart_infra
        ;;
    status)
        show_status
        ;;
    logs)
        view_logs
        ;;
    test)
        test_connectivity
        ;;
    clean)
        clean_data
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
