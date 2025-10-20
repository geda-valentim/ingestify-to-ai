#!/bin/bash

# Stop the API server
# This script finds and kills the uvicorn process running the API

echo "Stopping API server..."

# Find the process running uvicorn on port 8080
PID=$(lsof -ti:8080)

if [ -z "$PID" ]; then
    echo "No API server found running on port 8080"
    exit 0
fi

# Kill the process
kill $PID 2>/dev/null

if [ $? -eq 0 ]; then
    echo "API server stopped successfully (PID: $PID)"
else
    echo "Failed to stop API server. Trying with force..."
    kill -9 $PID 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "API server forcefully stopped (PID: $PID)"
    else
        echo "Failed to stop API server"
        exit 1
    fi
fi
