@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo        GHOST TRAIL / SENTINEL AI
echo =============================================

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :error
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :error

echo.
echo Checking frontend dependencies...
if not exist "dashboard\node_modules\.bin\vite.cmd" (
    echo Installing dashboard dependencies...
    cd dashboard
    call npm install
    if errorlevel 1 goto :error
    cd ..
)

echo.
echo Building dashboard...
cd dashboard
call npm run build
if errorlevel 1 goto :error
cd ..

echo.
echo Starting Sentinel AI...
python sentinel_app.py
exit /b %errorlevel%

:error
echo.
echo [ERROR] Startup/build failed. Check the message above.
pause
exit /b 1
