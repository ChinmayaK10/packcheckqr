@echo off
setlocal
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"

echo ========================================================
echo               Hotel QR Code Generator
echo ========================================================
echo.

:: Check if Python is installed
py -3 --version >nul 2>&1
if %errorlevel% neq 0 (
  python --version >nul 2>&1
  if %errorlevel% neq 0 (
    echo [ERROR] Python 3 is not installed on this computer.
    echo Please download and install Python from https://www.python.org/downloads/
    echo (Make sure to check "Add Python to PATH" during installation).
    echo.
    pause
    exit /b 1
  )
)

:: Automatically create virtual environment if missing
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating Python environment (.venv)...
  py -3 -m venv "%VENV%" 2>nul || python -m venv "%VENV%"
)

echo Installing required packages (qrcode, pillow)...
"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt" --quiet

echo Launching Hotel QR Generator...
start "" "%VENV%\Scripts\pythonw.exe" "%ROOT%qr_generator_app.py"

