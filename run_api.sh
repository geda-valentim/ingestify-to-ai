#!/bin/bash

# Run API locally on port 8080

# First, stop any existing API server
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "$SCRIPT_DIR/stop_api.sh" ]; then
    echo "🛑 Stopping existing API server..."
    bash "$SCRIPT_DIR/stop_api.sh"
    echo ""
fi

echo "🚀 Starting Ingestify API on port 8080..."
echo ""
echo "📋 Prerequisites:"
echo "   - Redis running on localhost:6379"
echo "   - Python dependencies installed (pip install -r backend/requirements.txt)"
echo ""
echo "🔗 Access:"
echo "   API: http://localhost:8080"
echo "   Docs: http://localhost:8080/docs"
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

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r backend/requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi
echo "✅ Dependencies installed"
echo ""

# Create temp directory
mkdir -p /tmp/ingestify

# Run API
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Add backend directory to PYTHONPATH so imports work correctly
export PYTHONPATH="$SCRIPT_DIR/backend:$PYTHONPATH"

# Set environment variables for local development
export REDIS_HOST="localhost"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
export ELASTICSEARCH_URL="http://localhost:9200"

uvicorn backend.api.main:app --host 0.0.0.0 --port 8080 --reload
