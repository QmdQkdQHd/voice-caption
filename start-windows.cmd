@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run install-windows.cmd first.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m voice_caption.app
if errorlevel 1 pause
