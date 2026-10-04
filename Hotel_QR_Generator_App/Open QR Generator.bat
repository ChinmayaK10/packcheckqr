@echo off
cd /d "%~dp0"

echo ========================================================
echo               Hotel QR Code Generator
echo ========================================================
echo.

:: Use system Python directly - simpler and always works
python --version >nul 2>&1
if %errorlevel% neq 0 (
  echo [ERROR] Python is not installed or not in PATH.
  echo Download from https://www.python.org/downloads/
  echo Make sure "Add Python to PATH" is checked.
  pause
  exit /b 1
)

echo Checking packages...
python -m pip install "qrcode[pil]>=7.4" "pillow>=10.2" --quiet

echo Launching Hotel QR Generator...
python qr_generator_app.py

if %errorlevel% neq 0 (
  echo.
  echo [ERROR] App crashed. See error above.
  pause
)
