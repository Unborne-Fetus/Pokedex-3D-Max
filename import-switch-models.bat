@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\import_switch_game_assets.py %*
) else (
  python scripts\import_switch_game_assets.py %*
)

if errorlevel 1 (
  echo.
  echo Switch model import failed.
  exit /b %errorlevel%
)

echo.
echo Switch model import finished.
endlocal
