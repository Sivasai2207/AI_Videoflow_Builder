#!/bin/bash
#
# AI VideoFlow Builder - Local Runner
#
# Starts all services for local development
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🎬 AI VideoFlow Builder${NC}"
echo "================================"
echo ""

# Check Redis
echo -n "Checking Redis... "
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}! Starting Redis...${NC}"
    redis-server --daemonize yes 2>/dev/null || {
        echo -e "${RED}✗ Failed to start Redis. Please install and start Redis manually.${NC}"
        exit 1
    }
    echo -e "${GREEN}✓ Started${NC}"
fi

# Check ComfyUI (optional)
echo -n "Checking ComfyUI... "
if curl -s http://127.0.0.1:8188/system_stats > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}! Not running (optional - mock images will be used)${NC}"
fi

# Check Ollama (optional)
echo -n "Checking Ollama... "
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${YELLOW}! Not running (optional - plan generation disabled)${NC}"
fi

echo ""
echo "================================"
echo "Starting services..."
echo ""

# Create data directories
mkdir -p data/db data/projects data/exports

# Start API
echo -e "${GREEN}Starting API server...${NC}"
cd apps/api
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Start API in background
uvicorn main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
cd ../..

# Give API time to start
sleep 2

# Start Worker
echo -e "${GREEN}Starting background worker...${NC}"
cd apps/worker
source ../api/venv/bin/activate
rq worker --with-scheduler &
WORKER_PID=$!
cd ../..

# Start Web UI
echo -e "${GREEN}Starting web UI...${NC}"
cd apps/web
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi
npm run dev &
WEB_PID=$!
cd ../..

echo ""
echo "================================"
echo -e "${GREEN}All services started!${NC}"
echo ""
echo "  📡 API:     http://localhost:8000"
echo "  📡 Docs:    http://localhost:8000/docs"
echo "  🌐 Web UI:  http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C and cleanup
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping services...${NC}"
    kill $API_PID 2>/dev/null
    kill $WORKER_PID 2>/dev/null
    kill $WEB_PID 2>/dev/null
    echo -e "${GREEN}Done!${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for any process to exit
wait
