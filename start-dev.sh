#!/bin/bash

# start-dev.sh - Script de desenvolvimento para FastAPI

# Define o diretório do projeto
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$PROJECT_DIR"

# Ativa o venv
source "$PROJECT_DIR/.venv/bin/activate"

# Log file
LOG_FILE="/tmp/guide-portal.log"

echo "=== Starting Guide Portal ===" | tee "$LOG_FILE"
echo "Logs: $LOG_FILE"
echo "Use: tail -f $LOG_FILE"
echo ""

# Inicia o servidor uvicorn com as mesmas configurações do launch.json
uvicorn app.main:app \
    --reload \
    --host 0.0.0.0 \
    --port 8001 \
    2>&1 | tee -a "$LOG_FILE"
