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
) else if /I "%~1"=="switch" (
  set "MODE=SWITCH"
  set "SETUP_ARGS=-SwitchAssetsOnly -SkipInstall"
) else if /I "%~1"=="fast" (
  set "MODE=FAST"
  set "SETUP_ARGS=-SkipModels -SkipSwitchAssets"
) else if exist "%~dp0.cache\switch-game-assets\pipeline-v9.ready.json" (
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
  echo   5. Restores existing original Switch GLBs
  echo   6. Allows unfinished textures; originals stay active
  echo      ^(converts cached original archives only if exports are missing^)
  echo   7. Builds Windows MSI/EXE installers
  echo      and automatically installs or updates the existing app
  echo.
  echo Existing downloads and conversions are reused whenever possible.
) else if "%MODE%"=="SWITCH" (
  echo SWITCH ASSET MODE:
  echo   Restores existing original Switch exports, including broken textures.
  echo   Converts cached original archives only when exported models are missing.
  echo   Runs importer syntax checks and self-tests.
  echo   Skips JDK, Gradle, generic model download, EXE build, and installer.
) else (
  echo FAST MODE:
  echo   Reuses your already-imported models and skips expensive asset work.
  echo   This is the default only after a fully validated v9 model import.
  echo   Run setup-all.bat switch to refresh Switch assets without rebuilding the app.
  echo   Run setup-all.bat full when you intentionally want the complete build pipeline.
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
  if "%MODE%"=="SWITCH" (
    echo Switch assets were synced and imported into:
    echo   %LOCALAPPDATA%\Pokedex3DMax\offline-models
  ) else (
    echo Windows installers:
    echo   %~dp0dist\Pokedex-3D-Max-Windows.msi
    echo   %~dp0dist\Pokedex-3D-Max-Windows.exe
    echo.
    echo Setup automatically installs or updates Pokedex 3D Max unless skipped.
  )
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

