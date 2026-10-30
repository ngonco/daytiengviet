@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failure
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failure
call npm ci --no-audit --no-fund
if errorlevel 1 goto failure
call npm run build
if errorlevel 1 goto failure
echo Da cai dat xong. Mo MO_VIETCUT.cmd de su dung.
pause
exit /b 0
:failure
echo Chua cai dat xong. Xem thong bao loi o tren.
pause
exit /b 1
