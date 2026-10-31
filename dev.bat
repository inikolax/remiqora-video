@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo            Remiqora Video - Launcher
echo ===================================================
echo.

:: 1. Virtual environment (first run only)
if not exist ".venv\Scripts\python.exe" (
    echo [Setup] Creating virtual environment...
    python -m venv .venv
    call ".venv\Scripts\python.exe" -m pip install --upgrade pip
    call ".venv\Scripts\pip.exe" install -r requirements.txt
)

:: An installed copy (the .exe installer) has the built page and not its sources: only the API, which serves the page
if not exist "frontend\package.json" (
    if not exist "frontend\dist\index.html" (
        echo [Error] The page is missing: frontend\dist - reinstall Remiqora Video
        pause
        exit /b 1
    )
    echo [Launcher] Starting Remiqora Video on http://127.0.0.1:8810 ...
    start "Remiqora API" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8810"
    timeout /t 3 /nobreak >nul
    start http://127.0.0.1:8810
    echo Close the "Remiqora API" window to stop it.
    exit /b 0
)

:: 2. The page and its packages (Vue HMR is served by Vite during development)
where npm >nul 2>nul
if errorlevel 1 (
    echo [Error] Node.js is not installed: https://nodejs.org
    pause
    exit /b 1
)
if not exist "frontend\node_modules" (
    echo [Setup] Installing the page's packages...
    call npm --prefix frontend install --no-audit --no-fund
)
:: the built page too, so http://127.0.0.1:8810 shows the current page and not the last build
echo [Launcher] Building the page...
call npm --prefix frontend run page
if errorlevel 1 (
    echo [Error] The page did not build
    pause
    exit /b 1
)

:: 3. API with Python auto-reload, and Vite with browser hot-module replacement
echo [Launcher] Starting API on http://127.0.0.1:8810 ...
start "Remiqora API" /D "%~dp0" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8810 --reload --reload-dir app"
echo [Launcher] Starting Vite on http://127.0.0.1:5173 ...
start "Remiqora UI" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1"

:: 4. Browser
echo [Launcher] Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5173

echo.
echo The engine starts by itself on the first shot (log in data\h3worker.log). Frontend edits hot-reload in the browser; Python edits restart the API. Close both "Remiqora API" and "Remiqora UI" windows to stop development servers.
echo ===================================================
endlocal
