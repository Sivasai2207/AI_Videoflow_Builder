#!/bin/bash

# Video Generator AI - Start All Services
# Run this script from the project root directory

echo "🚀 Starting Video Generator AI..."

# Start Redis in background
echo "📦 Starting Redis..."
redis-server --daemonize yes

# Start API
echo "🔧 Starting API server..."
cd apps/api
source venv/bin/activate
uvicorn main:app --reload --port 8000 &
API_PID=$!
cd ../..

# Start Worker
echo "⚙️  Starting worker..."
cd apps/worker
source ../api/venv/bin/activate
python main.py &
WORKER_PID=$!
cd ../..

# Start Frontend
echo "🌐 Starting frontend..."
cd apps/web
npm run dev &
FRONTEND_PID=$!
cd ../..

echo ""
echo "✅ All services started!"
echo ""
echo "   Frontend:  http://localhost:3000"
echo "   API:       http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait and cleanup
trap "kill $API_PID $WORKER_PID $FRONTEND_PID; redis-cli shutdown" SIGINT SIGTERM
wait
