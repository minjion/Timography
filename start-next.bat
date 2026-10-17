@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto error
)
".venv\Scripts\python.exe" -c "import PySide6, customtkinter" >nul 2>&1
if errorlevel 1 (
    echo Installing Timography Next dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements-next.txt
    if errorlevel 1 goto error
)
echo Opening Timography Next with its independent preview database...
".venv\Scripts\python.exe" main_qt.py
if errorlevel 1 goto error
exit /b 0

:error
echo Timography Next could not start. Review the error above.
pause
exit /b 1
