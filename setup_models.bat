@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_models.ps1" %*
exit /b %errorlevel%
