#!/bin/bash

# Run Celery worker locally

echo "⚙️  Starting Celery Worker..."
echo ""
echo "📋 Prerequisites:"
echo "   - Redis running on localhost:6379"
echo "   - Python dependencies installed (pip install -r requirements.txt)"
echo ""

# Check if Redis is running
if ! nc -z localhost 6379 2>/dev/null; then
    echo "❌ Redis is not running on localhost:6379"
    echo ""
    echo "Start Redis with:"
    echo "   docker run -d -p 6379:6379 --name doc2md-redis redis:7-alpine"
    echo ""
    exit 1
fi

echo "✅ Redis is running"
echo ""

# Create temp directory
mkdir -p /tmp/doc2md

# Run worker with isolated queue and unique hostname
cd /var/www/doc2md
celery -A workers.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    -Q doc2md \
    -n doc2md-worker@%h
