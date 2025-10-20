#!/bin/bash

# Run Celery worker locally

echo "⚙️  Starting Celery Worker..."
echo ""
echo "📋 Prerequisites:"
echo "   - Redis running on localhost:6379"
echo "   - Python dependencies installed (pip install -r backend/requirements.txt)"
echo ""

# Check if Redis is running
if ! nc -z localhost 6379 2>/dev/null; then
    echo "❌ Redis is not running on localhost:6379"
    echo ""
    echo "Start Redis with:"
    echo "   docker run -d -p 6379:6379 --name ingestify-redis redis:7-alpine"
    echo ""
    exit 1
fi

echo "✅ Redis is running"
echo ""

# Create temp directory
mkdir -p /tmp/ingestify

# Run worker with isolated queue and unique hostname
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Add backend directory to PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR/backend:$PYTHONPATH"

# Set environment variables for local development
export REDIS_HOST="localhost"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
export ELASTICSEARCH_URL="http://localhost:9200"

celery -A backend.workers.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    -Q ingestify \
    -n ingestify-worker@%h
