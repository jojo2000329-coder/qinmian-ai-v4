@echo off
setlocal
cd /d "%~dp0"

set "PORT=8765"
set "BUNDLED_PY=C:\Users\KyawNaing\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

title Qinmian Server
echo Qinmian server is starting at http://127.0.0.1:%PORT%/
echo Close this window to stop the app.
echo.

if exist "%BUNDLED_PY%" goto USE_BUNDLED

where py >nul 2>nul
if not errorlevel 1 goto USE_PY

where python >nul 2>nul
if not errorlevel 1 goto USE_PYTHON

echo Python was not found.
echo Install Python 3.10+ or run the app from Codex.
echo.
pause
exit /b 1

:USE_BUNDLED
set "PYTHON_EXE=%BUNDLED_PY%"
set "PYTHON_ARGS="
goto CHECK_RUNTIME

:USE_PY
set "PYTHON_EXE=py"
set "PYTHON_ARGS=-3"
goto CHECK_RUNTIME

:USE_PYTHON
set "PYTHON_EXE=python"
set "PYTHON_ARGS="

:CHECK_RUNTIME
"%PYTHON_EXE%" %PYTHON_ARGS% -c "import flask, flask_cors, openpyxl, pypdf, docx" >nul 2>nul
if not errorlevel 1 goto RUN_SERVER

echo First run: installing the web runtime...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r "%~dp0requirements-runtime.txt"
if errorlevel 1 goto INSTALL_FAILED

:RUN_SERVER
"%PYTHON_EXE%" %PYTHON_ARGS% app.py %PORT%
goto END

:INSTALL_FAILED
echo.
echo The required web runtime could not be installed.
echo Check the network connection, then double-click the launcher again.
pause
exit /b 1

:END
echo.
echo Qinmian server stopped.
pause
exit /b 0
