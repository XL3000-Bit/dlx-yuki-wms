@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\uvicorn.exe" (
  echo Backend virtual environment not found: backend\.venv
  pause
  exit /b 1
)
if not exist "frontend\package.json" (
  echo Frontend package.json not found.
  pause
  exit /b 1
)

echo Starting DLX Yuki WMS backend on http://0.0.0.0:8000 ...
start "DLX WMS Backend" cmd /k "pushd %~dp0backend && .venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000"

echo Starting DLX Yuki WMS frontend on http://0.0.0.0:5173 ...
start "DLX WMS Frontend" cmd /k "pushd %~dp0frontend && npm run dev -- --host 0.0.0.0"

echo.
echo DLX Yuki WMS is starting.
echo Local:   http://127.0.0.1:5173
echo LAN:     http://YOUR-PC-IP:5173
echo Backend: http://YOUR-PC-IP:8000/docs
echo.
endlocal
