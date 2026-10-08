@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Pokedex 3D Max - One-Click Setup

set "SETUP_ARGS="
set "MODE=FULL"

rem Normal reruns should be fast once imported assets already exist.
rem Use "setup-all.bat full" to force the complete asset/setup pipeline.
if /I "%~1"=="full" (
  set "MODE=FULL"
) else if /I "%~1"=="fast" (
  set "MODE=FAST"
  set "SETUP_ARGS=-SkipModels -SkipSwitchAssets"
) else if exist "%~dp0web\models\switch-manifest.json" (
  set "MODE=FAST"
  set "SETUP_ARGS=-SkipModels -SkipSwitchAssets"
)

echo ============================================================
echo            Pokedex 3D Max - One-Click Setup
echo ============================================================
echo.
echo Mode: %MODE%
echo.
if "%MODE%"=="FULL" (
  echo This setup automatically:
  echo   1. Reuses/installs JDK
  echo   2. Reuses/installs Gradle
  echo   3. Reuses/installs Python + Pillow
  echo   4. Reuses/installs Blender
  echo   5. Detects and imports Switch Pokemon model archives
  echo   6. Reuses/downloads missing offline models
  echo   7. Builds the Windows EXE
  echo.
  echo Existing downloads and conversions are reused whenever possible.
) else (
  echo FAST MODE:
  echo   Reuses your already-imported models and skips expensive asset work.
  echo   This is now the default after the first successful model import.
  echo   Run setup-all.bat full only when you intentionally want to refresh assets.
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

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_all.ps1" %SETUP_ARGS%
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%EXITCODE%"=="0" (
  echo Setup finished successfully.
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
