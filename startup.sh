#!/bin/bash
# Azure App Service startup script for FastAPI application

# Exit on error
set -e

echo "Starting Guide Portal application..."

# Get the port from environment variable (Azure sets this)
PORT="${PORT:-8000}"

# Start Gunicorn with Uvicorn workers for ASGI support
echo "Starting Gunicorn server on port $PORT..."
gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind "0.0.0.0:$PORT" \
    --timeout 600 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
