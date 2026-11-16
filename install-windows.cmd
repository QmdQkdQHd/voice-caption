@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -e .
if errorlevel 1 goto fail
echo Installation complete. Run start-windows.cmd next.
pause
exit /b 0
:fail
echo Installation failed. Install Python 3.11 64-bit and try again.
pause
exit /b 1
