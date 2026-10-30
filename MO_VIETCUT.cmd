@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "dist\index.html" (
  echo Chua co giao dien da build. Hay chay CAI_DAT.cmd truoc.
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" start.py
) else (
  python start.py
)
if errorlevel 1 pause
