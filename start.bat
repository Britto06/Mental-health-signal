@echo off
echo ============================================
echo   Mental Health Signal - Starting servers
echo ============================================
echo.

echo Starting Backend (FastAPI) on port 8000...
if exist "%~dp0.venv\Scripts\activate.bat" (
    start "Backend - FastAPI" cmd /k "cd /d \"%~dp0\" && call .venv\Scripts\activate && python -m uvicorn api:app --reload --port 8000"
) else (
    start "Backend - FastAPI" cmd /k "cd /d \"%~dp0\" && python -m uvicorn api:app --reload --port 8000"
)

timeout /t 3 /nobreak > nul

echo Starting Frontend (React) on port 5173...
start "Frontend - React" cmd /k "cd /d \"%~dp0mental-health-signal\" && npm run dev"

timeout /t 5 /nobreak > nul

echo.
echo ============================================
echo   Both servers are starting!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo ============================================
echo.
echo Opening the app in your browser...
start http://localhost:5173

echo Press any key to close this window...
pause > nul
