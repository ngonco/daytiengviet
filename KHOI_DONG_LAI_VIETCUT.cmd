@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\restart_vietcut.py"
) else (
  python "scripts\restart_vietcut.py"
)
if errorlevel 1 pause
