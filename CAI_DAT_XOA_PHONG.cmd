@echo off
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -X utf8 scripts\setup_matting.py
) else (
  python -X utf8 scripts\setup_matting.py
)
if errorlevel 1 (
  echo Installation did not finish. Check the connection and free disk space, then retry.
) else (
  echo Ready. Open VietCut and refresh the background-removal status.
)
pause
