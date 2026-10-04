@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHON=python"
if exist "%ROOT%\..\.venv\Scripts\python.exe" set "PYTHON=%ROOT%\..\.venv\Scripts\python.exe"

cd /d "%ROOT%\demo_main_backend"
"%PYTHON%" demo_main_backend.py
