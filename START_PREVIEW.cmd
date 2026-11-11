@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto setup
where py >nul 2>&1
if errorlevel 1 (
    python -m venv .venv
) else (
    py -3 -m venv .venv
)
if errorlevel 1 goto fail
:setup
if not exist ".venv\preview-installed" (
    ".venv\Scripts\python.exe" -m pip install -r requirements-preview.txt
    if errorlevel 1 goto fail
    type nul > ".venv\preview-installed"
)
".venv\Scripts\python.exe" start_preview.py %*
if errorlevel 1 goto fail
exit /b 0
:fail
echo Preview failed. Check Python 3.11 or newer, internet for first setup, and port availability.
pause
exit /b 1
