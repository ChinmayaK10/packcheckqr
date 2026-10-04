@echo off
cd /d "%~dp0"

echo ========================================================
echo               Hotel QR Code Generator
echo ========================================================
echo.

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
  py -3 --version >nul 2>&1
  if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Download from https://www.python.org/downloads/
    echo Make sure "Add Python to PATH" is checked.
    pause
    exit /b 1
  )
  set "PY=py -3"
) else (
  set "PY=python"
)

:: Create venv if needed
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PY% -m venv .venv
)

:: Install/upgrade deps
echo Checking packages...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet --disable-pip-version-check

echo Launching Hotel QR Generator...
.venv\Scripts\pythonw.exe qr_generator_app.py

if %errorlevel% neq 0 (
  echo.
  echo [ERROR] App crashed. See error above.
  .venv\Scripts\python.exe qr_generator_app.py
  pause
)
