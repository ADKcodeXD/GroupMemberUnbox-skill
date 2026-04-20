@echo off
setlocal EnableExtensions

cd /d "%~dp0"
if not exist "%~dp0.tmp" mkdir "%~dp0.tmp" >nul 2>nul
set "TMP=%~dp0.tmp"
set "TEMP=%~dp0.tmp"

set "PYTHON_CMD="
if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON_CMD=""%~dp0.venv\Scripts\python.exe"""
if not defined PYTHON_CMD if exist "%~dp0venv\Scripts\python.exe" set "PYTHON_CMD=""%~dp0venv\Scripts\python.exe"""
if not defined PYTHON_CMD if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" set "PYTHON_CMD=""%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"""

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    where py >nul 2>nul
    if %ERRORLEVEL%==0 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    echo [ERROR] Python was not found in PATH.
    echo [HINT] Install Python 3.10+ and try again.
    pause
    exit /b 1
)

%PYTHON_CMD% -c "import PyQt5" >nul 2>nul
if not "%ERRORLEVEL%"=="0" (
    echo [INFO] Missing GUI dependencies. Installing from requirements.txt...
    %PYTHON_CMD% -m pip install --user --no-cache-dir -r requirements.txt
    if not "%ERRORLEVEL%"=="0" (
        echo [ERROR] Dependency install failed.
        echo [HINT] Check network and pip mirror, then run: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo [INFO] Starting GUI...
%PYTHON_CMD% profiler_gui.py
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Startup failed. Exit code: %EXIT_CODE%
    echo [HINT] Try: pip install -r requirements.txt
    pause
)

exit /b %EXIT_CODE%
