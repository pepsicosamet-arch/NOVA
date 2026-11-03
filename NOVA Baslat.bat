@echo off
setlocal
cd /d "%~dp0"
if exist "dist\NOVA\NOVA.exe" (
  start "" "dist\NOVA\NOVA.exe"
  exit /b 0
)
if not exist ".venv\Scripts\python.exe" (
  echo NOVA henuz kurulmamis. Once build.bat'i calistir.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py
