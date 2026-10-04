@echo off
setlocal
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"

if exist "%ROOT%..\.venv\Scripts\python.exe" set "VENV=%ROOT%..\.venv"

if not exist "%VENV%\Scripts\python.exe" (
  py -3 -m venv "%VENV%"
)

"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%qr_generator\requirements.txt"
start "" "%VENV%\Scripts\pythonw.exe" "%ROOT%qr_generator\qr_generator_app.py"
