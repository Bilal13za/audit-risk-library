@echo off
REM Audit Risk and Evidence Library - double-click this file to start the app.
echo [Audit Risk and Evidence Library launcher]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
echo.
echo Exit code: %ERRORLEVEL%
echo If the app did not start, open launch.log in this folder and send it for help.
pause
