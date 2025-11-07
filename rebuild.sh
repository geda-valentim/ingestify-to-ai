#!/bin/bash

echo "======================================"
echo "  Doc2MD - Rebuild and Start"
echo "======================================"
echo ""

# Enable BuildKit for better caching and faster builds
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "Stopping existing containers..."
sudo docker compose down

echo ""
echo "Building and starting with updated requirements..."
sudo -E docker compose up -d --build

echo ""
echo "Waiting for services to initialize..."
sleep 15

echo ""
echo "======================================"
echo "  Service Status"
echo "======================================"
sudo docker compose ps

echo ""
echo "======================================"
echo "  Container Logs (last 20 lines)"
echo "======================================"
echo ""
echo "--- API Logs ---"
sudo docker compose logs --tail=20 api

echo ""
echo "--- Worker Logs ---"
sudo docker compose logs --tail=20 worker

echo ""
echo "======================================"
echo "  Testing API Health Check"
echo "======================================"
sleep 5
curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "⚠️  API not ready yet, wait a few more seconds and try: curl http://localhost:8080/health"

echo ""
echo ""
echo "======================================"
echo "  ✅ Setup Complete!"
echo "======================================"
echo "  API Documentation: http://localhost:8080/docs"
echo "  Health Check:      http://localhost:8080/health"
echo ""
echo "To view live logs:"
echo "  sudo docker compose logs -f"
echo "======================================"
