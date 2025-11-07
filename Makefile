.PHONY: help start stop restart logs status clean infra-start infra-stop infra-status ps build rebuild dev prod scale test

# Default target
.DEFAULT_GOAL := help

# ======================================
# COLORS
# ======================================
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[1;33m
RED := \033[0;31m
NC := \033[0m # No Color

# ======================================
# HELP
# ======================================
help: ## Show this help message
	@echo ""
	@echo "$(CYAN)Ingestify - Docker Compose Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Main Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make start          # Start with auto-detection"
	@echo "  make infra-start    # Start shared infrastructure"
	@echo "  make logs           # View all logs"
	@echo "  make scale n=10     # Scale workers to 10 replicas"
	@echo ""

# ======================================
# APPLICATION COMMANDS
# ======================================
start: ## Start application (auto-detect shared infrastructure)
	@./start.sh

stop: ## Stop all services
	@echo "$(YELLOW)🛑 Stopping services...$(NC)"
	@docker compose down

restart: stop start ## Restart all services

logs: ## View logs from all services (Ctrl+C to stop)
	@docker compose logs -f

status: ps ## Show service status

ps: ## Show running containers
	@echo ""
	@echo "$(CYAN)Service Status:$(NC)"
	@docker compose ps
	@echo ""

build: ## Build all services without starting
	@echo "$(YELLOW)🔨 Building services...$(NC)"
	@docker compose build

rebuild: ## Rebuild and restart all services
	@./rebuild.sh

# ======================================
# INFRASTRUCTURE COMMANDS
# ======================================
infra-start: ## Start shared infrastructure (Redis, MinIO, Elasticsearch)
	@echo "$(CYAN)📦 Starting shared infrastructure...$(NC)"
	@docker compose -f docker-compose.infra.yml up -d
	@echo ""
	@echo "$(GREEN)✅ Shared infrastructure started!$(NC)"
	@echo "   Redis:         localhost:6379"
	@echo "   MinIO:         http://localhost:9000"
	@echo "   MinIO UI:      http://localhost:9001 (minioadmin/minioadmin)"
	@echo "   Elasticsearch: http://localhost:9200"
	@echo ""

infra-stop: ## Stop shared infrastructure
	@echo "$(YELLOW)🛑 Stopping shared infrastructure...$(NC)"
	@docker compose -f docker-compose.infra.yml down

infra-status: ## Show shared infrastructure status
	@echo ""
	@echo "$(CYAN)Shared Infrastructure Status:$(NC)"
	@docker compose -f docker-compose.infra.yml ps
	@echo ""

infra-logs: ## View shared infrastructure logs
	@docker compose -f docker-compose.infra.yml logs -f

# ======================================
# DEVELOPMENT COMMANDS
# ======================================
dev: ## Start in development mode with hot reload
	@echo "$(CYAN)🔧 Starting development mode...$(NC)"
	@docker compose up -d
	@echo "$(GREEN)✅ Development mode ready!$(NC)"

prod: ## Start in production mode
	@echo "$(CYAN)🚀 Starting production mode...$(NC)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "$(GREEN)✅ Production mode ready!$(NC)"

scale: ## Scale workers (usage: make scale n=10)
	@if [ -z "$(n)" ]; then \
		echo "$(RED)❌ Error: Please specify number of workers (e.g., make scale n=10)$(NC)"; \
		exit 1; \
	fi
	@echo "$(CYAN)⚙️  Scaling workers to $(n) replicas...$(NC)"
	@docker compose up -d --scale worker=$(n) --no-recreate
	@echo "$(GREEN)✅ Workers scaled to $(n)$(NC)"

# ======================================
# TESTING COMMANDS
# ======================================
test: ## Run backend tests
	@echo "$(CYAN)🧪 Running tests...$(NC)"
	@docker compose exec api pytest tests/ -v

test-api: ## Test API health
	@echo "$(CYAN)🔍 Testing API...$(NC)"
	@curl -s http://localhost:8000/health | python3 -m json.tool || echo "$(RED)API not responding$(NC)"

# ======================================
# CLEANUP COMMANDS
# ======================================
clean: ## Stop all services and remove volumes
	@echo "$(RED)⚠️  This will remove all data. Are you sure? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(YELLOW)🧹 Cleaning up...$(NC)"
	@docker compose down -v
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

clean-infra: ## Stop shared infrastructure and remove volumes
	@echo "$(RED)⚠️  This will remove shared infrastructure data. Are you sure? [y/N]$(NC)" && read ans && [ $${ans:-N} = y ]
	@echo "$(YELLOW)🧹 Cleaning shared infrastructure...$(NC)"
	@docker compose -f docker-compose.infra.yml down -v
	@echo "$(GREEN)✅ Infrastructure cleanup complete$(NC)"

prune: ## Remove all unused Docker resources
	@echo "$(YELLOW)🧹 Pruning Docker system...$(NC)"
	@docker system prune -a --volumes -f
	@echo "$(GREEN)✅ Prune complete$(NC)"

# ======================================
# LOGS & DEBUG
# ======================================
logs-api: ## View API logs
	@docker compose logs -f api

logs-worker: ## View worker logs
	@docker compose logs -f worker

logs-beat: ## View beat logs
	@docker compose logs -f beat

logs-frontend: ## View frontend logs
	@docker compose logs -f frontend

logs-redis: ## View Redis logs (local or shared)
	@if docker ps | grep -q "shared-redis"; then \
		docker logs -f shared-redis; \
	else \
		docker compose logs -f redis; \
	fi

logs-minio: ## View MinIO logs (local or shared)
	@if docker ps | grep -q "shared-minio"; then \
		docker logs -f shared-minio; \
	else \
		docker compose logs -f minio; \
	fi

shell-api: ## Open shell in API container
	@docker compose exec api bash

shell-worker: ## Open shell in worker container
	@docker compose exec worker bash

# ======================================
# NETWORK & DIAGNOSTICS
# ======================================
network-ls: ## List all Docker networks
	@docker network ls

network-inspect: ## Inspect ingestify network
	@docker network inspect ingestify-network 2>/dev/null || echo "$(YELLOW)Network not found$(NC)"

ps-all: ## Show all containers (including stopped)
	@docker ps -a

images: ## List all images
	@docker images

# ======================================
# QUICK ACTIONS
# ======================================
api-restart: ## Restart only API
	@docker compose restart api

worker-restart: ## Restart only workers
	@docker compose restart worker

frontend-restart: ## Restart only frontend
	@docker compose restart frontend

all-restart: api-restart worker-restart frontend-restart ## Restart all app services
