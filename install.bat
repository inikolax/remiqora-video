@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo        Remiqora Video - clean installation
echo ===================================================
echo.
echo.

where git >nul 2>nul
if errorlevel 1 goto prereqs
where uv >nul 2>nul
if errorlevel 1 goto prereqs
py -3.13 --version >nul 2>nul
if errorlevel 1 goto prereqs

call powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_models.ps1" %*
exit /b %errorlevel%

:prereqs
call "%~dp0setup_prereqs.bat"
echo.
echo If prerequisites were installed, close this window, open a new terminal, and run install.bat again.
pause
exit /b 1
endlocal
