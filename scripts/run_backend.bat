@echo off
setlocal
set "ROOT=%~dp0.."
set "VENV=%ROOT%\.venv"

if exist "%ROOT%\..\.venv\Scripts\python.exe" set "VENV=%ROOT%\..\.venv"

if not exist "%VENV%\Scripts\python.exe" (
  py -3 -m venv "%VENV%"
)

"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%\backend\requirements.txt"
cd /d "%ROOT%\backend"
"%VENV%\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
