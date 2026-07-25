@echo off
cd /d "%~dp0"
echo.
echo Qinmian is running at http://127.0.0.1:8765/
echo Keep this window open. Press Ctrl+C to stop.
echo.
"C:\Users\KyawNaing\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py 8765
pause
