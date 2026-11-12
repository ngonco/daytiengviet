@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\restart_vietcut.py" --sync-github
) else (
  python "scripts\restart_vietcut.py" --sync-github
)
if errorlevel 1 pause
