@echo off
setlocal
cd /d "%~dp0"

set "PORT=8765"
set "URL=http://127.0.0.1:%PORT%/"

title Qinmian Launcher
echo ========================================
echo Qinmian AI Launcher
echo ========================================
echo.

netstat -ano | find "127.0.0.1:%PORT%" | find "LISTENING" >nul
if not errorlevel 1 goto OPEN_SITE

echo Starting Qinmian server...
start "Qinmian Server" cmd /k call "%~dp0qinmian_server.cmd"

echo Waiting for server...
timeout /t 2 /nobreak >nul

:OPEN_SITE
echo Opening:
echo %URL%
echo.
start "" "%URL%"
echo If the browser did not open, copy the URL above.
echo Keep the "Qinmian Server" window open while using the app.
echo.
pause
exit /b 0
