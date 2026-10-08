@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Pokedex 3D Max - Import Switch Models

echo ============================================================
echo          Pokedex 3D Max - Import Switch Models
echo ============================================================
echo.
if "%~1"=="" (
  echo No archive paths were supplied.
  echo Auto-detecting assets downloaded by setup-all...
  echo.
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -u scripts\import_switch_game_assets.py %*
) else (
  python -u scripts\import_switch_game_assets.py %*
)

set "EXITCODE=%ERRORLEVEL%"
echo.
echo ============================================================
if not "%EXITCODE%"=="0" (
  echo Switch model import failed with error code %EXITCODE%.
  echo.
  echo The window will stay open so you can read the error.
) else (
  echo Switch model import finished successfully.
)
echo ============================================================
echo.
pause
exit /b %EXITCODE%
