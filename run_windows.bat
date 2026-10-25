@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo The app is not set up yet. Double-click setup_windows.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" run.py %*
if errorlevel 1 pause
