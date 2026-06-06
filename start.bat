@echo off
REM ============================================================
REM  SynaptDI launcher for Windows  (double-click or run in cmd)
REM  Prereqs (one-time): see README "Windows setup".
REM ============================================================
cd /d "%~dp0"

echo.
echo   SynaptDI - starting...
echo   ----------------------------------------

REM 1) Ollama
echo [1/3] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
  echo    Ollama not running - launching it in a new window...
  start "Ollama" ollama serve
  timeout /t 4 >nul
) else (
  echo    Ollama is running.
)

REM 2) Backend  (first run builds the index, then starts the API)
if not exist "backend\chroma_db" (
  echo [2/3] No index yet - first run will clone + index TM Forum ^(~5-10 min^).
  start "SynaptDI Backend" cmd /k "cd backend && venv\Scripts\activate && python ingest.py && uvicorn main:app --host 0.0.0.0 --port 8000"
) else (
  echo [2/3] Starting backend API...
  start "SynaptDI Backend" cmd /k "cd backend && venv\Scripts\activate && uvicorn main:app --host 0.0.0.0 --port 8000"
)

REM 3) Frontend
echo [3/3] Starting frontend...
start "SynaptDI Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo   Opening in separate windows. Give it ~15s, then visit:
echo     http://localhost:3000
echo.
pause
