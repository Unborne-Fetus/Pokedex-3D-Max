@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Pokedex 3D Max - Windows Setup

set "MODE=FAST"
set "MODEL_ARGS=-SkipModels"

if /I "%~1"=="full" (
  set "MODE=FULL"
  set "MODEL_ARGS=-RefreshModels"
)

echo ============================================================
echo              Pokedex 3D Max - Windows Setup
echo ============================================================
echo.
echo Mode: %MODE%
echo.
if "%MODE%"=="FAST" (
  echo FAST SETUP ^(recommended^)
  echo.
  echo This setup will:
  echo   1. Reuse/download JDK only if needed
  echo   2. Reuse/download Gradle only if needed
  echo   3. Skip the huge offline model sync
  echo   4. Build the Windows EXE using Gradle cache/parallel mode
  echo.
  echo Existing offline models are still reused if you already have them.
  echo The app can use online model sources when no offline pack exists.
  echo.
  echo To refresh/download the COMPLETE offline model pack, run:
  echo   setup-all.bat full
) else (
  echo FULL OFFLINE SETUP
  echo.
  echo This also refreshes/downloads the complete offline 3D model pack.
  echo This mode can take much longer.
)
echo.
echo Live progress is saved to setup-all.log.
echo.
echo Press any key to begin.
pause >nul
echo.

if not exist "%~dp0scripts\setup_all.ps1" (
  echo ERROR: scripts\setup_all.ps1 is missing.
  echo Run git pull, then launch setup-all.bat again.
  echo.
  pause
  exit /b 2
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_all.ps1" %MODEL_ARGS%
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%EXITCODE%"=="0" (
  echo Windows setup finished.
  echo.
  echo Final installer:
  echo   %~dp0dist\Pokedex-3D-Max-Windows.exe
) else (
  echo Setup failed with error code %EXITCODE%.
  echo.
  echo Full log:
  echo   %~dp0setup-all.log
)
echo ============================================================
echo.
pause
exit /b %EXITCODE%
