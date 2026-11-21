@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m venv .venv-build
if errorlevel 1 goto fail
.venv-build\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
rem CPU-only Torch prevents bundling unnecessary CUDA runtime packages.
.venv-build\Scripts\python.exe -m pip install torch==2.15.0+cpu --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto fail
.venv-build\Scripts\python.exe -m pip install -r packaging/requirements-windows.txt -e .
if errorlevel 1 goto fail
.venv-build\Scripts\python.exe -m pip check
if errorlevel 1 goto fail
.venv-build\Scripts\python.exe scripts\build_windows.py
if errorlevel 1 goto fail
echo Build and packaged self-test complete. See release folder.
pause
exit /b 0
:fail
echo Build failed. Read the error above. Do not distribute a partial build.
pause
exit /b 1
