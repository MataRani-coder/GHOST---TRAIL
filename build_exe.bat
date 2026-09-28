@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

echo ============================================================
echo   GHOST TRAIL - Build .exe Desktop Application
echo ============================================================
echo.

:: ── Change to script directory ─────────────────────────────────────────────
cd /d "%~dp0"

:: ── Step 1: Install Python dependencies ───────────────────────────────────
echo [1/5] Installing Python packaging dependencies...
pip install pyinstaller pywebview pystray pillow fastapi uvicorn pyyaml --quiet
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pip install failed. Check your Python environment.
    pause
    exit /b 1
)
echo        Done.
echo.

:: ── Step 2: Build React dashboard ─────────────────────────────────────────
echo [2/5] Building React dashboard...
cd dashboard
call npm install --silent
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] npm install failed.
    pause
    exit /b 1
)
call npm run build
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] npm run build failed.
    pause
    exit /b 1
)
cd ..
echo        Done. (dashboard/dist/ created)
echo.

:: ── Step 3: Generate app icon ──────────────────────────────────────────────
echo [3/5] Generating app icon...
python create_icon.py
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Icon generation failed - using default icon.
    mkdir assets 2>nul
    :: Create a minimal placeholder ICO if icon gen fails
)
echo        Done.
echo.

:: ── Step 4: Run PyInstaller ────────────────────────────────────────────────
echo [4/5] Running PyInstaller (this takes 3-10 minutes)...
echo        Bundling Python runtime, AI models, and React dashboard...
echo.
pyinstaller sentinel.spec --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller failed. See above for details.
    pause
    exit /b 1
)
echo.
echo        Done. Output: dist\sentinel\sentinel.exe
echo.

:: ── Step 5: Create desktop shortcut ───────────────────────────────────────
echo [5/5] Creating desktop shortcut...
set SHORTCUT_PATH=%USERPROFILE%\Desktop\Ghost Trail.lnk
set TARGET_PATH=%~dp0dist\sentinel\sentinel.exe
set ICON_PATH=%~dp0dist\sentinel\sentinel.exe

powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); ^
   $s.TargetPath = '%TARGET_PATH%'; ^
   $s.WorkingDirectory = '%~dp0dist\sentinel'; ^
   $s.IconLocation = '%ICON_PATH%'; ^
   $s.Description = 'Ghost Trail Perimeter Defense'; ^
   $s.Save()"

if %ERRORLEVEL% EQU 0 (
    echo        Desktop shortcut created: "Ghost Trail.lnk"
) else (
    echo [WARN] Could not create desktop shortcut.
)

echo.
echo ============================================================
echo   BUILD COMPLETE!
echo ============================================================
echo.
echo   Executable: %~dp0dist\sentinel\sentinel.exe
echo   Desktop shortcut: %USERPROFILE%\Desktop\Ghost Trail.lnk
echo.
echo   Double-click sentinel.exe or the desktop shortcut to launch.
echo   The app will open with a splash screen, then the dashboard.
echo.
pause
