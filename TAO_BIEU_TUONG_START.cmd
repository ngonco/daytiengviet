@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -X utf8 scripts\install_start_shortcuts.py
) else (
  python -X utf8 scripts\install_start_shortcuts.py
)
if errorlevel 1 (
  echo Could not create shortcuts. Check the message above.
) else (
  echo Ready. Find Vietnamese with Vinh in Start, then right-click and choose Pin to Start.
)
pause
