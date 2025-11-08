#!/bin/bash
# Validate frontend TypeScript before Docker build
# Run this script before running docker compose up to catch TS errors early

set -e

echo "🔍 Validating frontend TypeScript..."

cd "$(dirname "$0")/frontend"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install --legacy-peer-deps
fi

# Run TypeScript check only (faster than full build)
echo "🔎 Checking TypeScript types..."
npx tsc --noEmit

# Clean up .next if it was created
if [ -d ".next" ]; then
    echo "🧹 Cleaning up .next folder..."
    rm -rf .next
fi

echo "✅ Frontend validation passed! Safe to run docker compose up."
