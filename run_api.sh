#!/bin/bash

# Run API locally on port 8080

echo "🚀 Starting Doc2MD API on port 8080..."
echo ""
echo "📋 Prerequisites:"
echo "   - Redis running on localhost:6379"
echo "   - Python dependencies installed (pip install -r requirements.txt)"
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
    echo "   docker run -d -p 6379:6379 --name doc2md-redis redis:7-alpine"
    echo ""
    exit 1
fi

echo "✅ Redis is running"
echo ""

# Create temp directory
mkdir -p /tmp/doc2md

# Run API
cd /var/www/doc2md
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
