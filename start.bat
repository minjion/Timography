@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import customtkinter, pystray, PIL, apscheduler, pynput, windows_toasts" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
echo Starting Timography...
".venv\Scripts\python.exe" main.py
if errorlevel 1 goto error
exit /b 0

:error
echo Timography could not start. Review the error above.
pause
exit /b 1
