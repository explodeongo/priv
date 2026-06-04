#!/bin/bash
# SynaptDI — Start Everything

set -e
RED='\033[0;31m'; GREEN='\033[0;32m'; GRAY='\033[0;37m'; NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"
VENV="$BACKEND/venv/bin/activate"

echo ""
echo -e "${RED}  SynaptDI${NC}"
echo -e "${GRAY}  Enterprise domains at your fingertips${NC}"
echo "  ─────────────────────────────────"

# 1. Check Ollama
echo ""
echo -e "${GRAY}[1/3] Checking Ollama...${NC}"
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  Starting Ollama in background..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 4
fi
echo -e "${GREEN}  ✓ Ollama running${NC}"

# 2. Build index if needed
CHROMA="$BACKEND/chroma_db"
if [ ! -d "$CHROMA" ] || [ -z "$(ls -A $CHROMA 2>/dev/null)" ]; then
    echo ""
    echo -e "${GRAY}[2/3] No index found. Running ingestion (~5 mins first time)...${NC}"
    cd "$BACKEND"
    source "$VENV"
    python3 ingest.py
else
    echo -e "${GREEN}  ✓ Index found${NC}"
fi

# 3. Kill anything on ports 8000/3000
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

echo ""
echo -e "${GRAY}[3/3] Starting services...${NC}"

# Start backend with venv
cd "$BACKEND"
source "$VENV"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload > "$SCRIPT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

# Start frontend
cd "$FRONTEND"
npm run dev > "$SCRIPT_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!

sleep 4

# Verify backend is up
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo ""
    echo "  ─────────────────────────────────"
    echo -e "${GREEN}  ✓ SynaptDI is running!${NC}"
    echo ""
    echo "  Chat UI:   http://localhost:3000"
    echo "  API docs:  http://localhost:8000/docs"
    echo "  Health:    http://localhost:8000/health"
    echo ""
    echo -e "${GRAY}  Press Ctrl+C to stop${NC}"
    echo "  ─────────────────────────────────"
else
    echo -e "${RED}  ✗ Backend failed to start. Check backend.log${NC}"
    cat "$SCRIPT_DIR/backend.log" | tail -20
fi

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" INT TERM
wait $BACKEND_PID $FRONTEND_PID