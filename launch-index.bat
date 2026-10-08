@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\launch_index.py
) else (
  python scripts\launch_index.py
)
if errorlevel 1 pause
