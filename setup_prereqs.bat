@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_prereqs.ps1" %*
exit /b %errorlevel%
