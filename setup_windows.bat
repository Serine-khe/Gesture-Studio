@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================================
echo   Gesture Studio - one-time setup (Windows)
echo ================================================
echo.

rem Find a Python version that MediaPipe supports (3.9 - 3.12), preferring 3.11.
set "PY="
for %%V in (3.11 3.12 3.10 3.9) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,9) <= sys.version_info[:2] <= (3,12) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [!] Could not find Python 3.9 - 3.12.
    echo     Install Python 3.11 from https://www.python.org/downloads/windows/
    echo     and tick "Add python.exe to PATH" in the installer. Then run this file again.
    echo.
    pause
    exit /b 1
)
echo Using Python: %PY%
%PY% --version

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Creating virtual environment in .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [!] Could not create the virtual environment. See README.md - Troubleshooting.
        pause
        exit /b 1
    )
)

echo.
echo Installing packages (this can take a few minutes the first time) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [!] Package installation failed. See README.md - Troubleshooting.
    pause
    exit /b 1
)

echo.
echo Checking camera and speakers ...
".venv\Scripts\python.exe" run.py --check
echo.
echo Setup finished! Double-click run_windows.bat to start Gesture Studio.
pause
