@echo off
setlocal

set ROOT=%~dp0

if not exist "%ROOT%backend\.env" (
  echo [!] No backend\.env yet. Copying from .env.example.
  copy "%ROOT%backend\.env.example" "%ROOT%backend\.env" >nul
  echo     Edit backend\.env to set REPLAY_DIR and MY_PLAYER_NAMES, then re-run.
  pause
  exit /b 1
)

echo [+] Starting backend on http://127.0.0.1:8765
start "sc2-backend" cmd /k "cd /d %ROOT%backend && .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765"

echo [+] Starting frontend on http://localhost:5173
start "sc2-frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo Open http://localhost:5173 in your browser.
echo Close the two terminal windows to stop.
