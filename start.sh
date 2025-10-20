#!/bin/bash

echo "======================================"
echo "  Doc2MD API - Starting Services"
echo "======================================"
echo ""

# Check if docker group membership needs refresh
if ! groups | grep -q docker; then
    echo "Note: You may need to add your user to the docker group:"
    echo "  sudo usermod -aG docker \$USER"
    echo "  newgrp docker"
    echo ""
fi

echo "Building and starting services..."
docker compose up -d --build

echo ""
echo "Waiting for services to be ready..."
sleep 10

echo ""
echo "======================================"
echo "  Service Status"
echo "======================================"
docker compose ps

echo ""
echo "======================================"
echo "  API Health Check"
echo "======================================"
curl -s http://localhost:8080/health | python3 -m json.tool || echo "API not ready yet"

echo ""
echo "======================================"
echo "  Access Points"
echo "======================================"
echo "  API:            http://localhost:8080"
echo "  API Docs:       http://localhost:8080/docs"
echo "  Health Check:   http://localhost:8080/health"
echo ""
echo "To view logs:"
echo "  docker compose logs -f api"
echo "  docker compose logs -f worker"
echo ""
echo "To stop services:"
echo "  docker compose down"
echo "======================================"
