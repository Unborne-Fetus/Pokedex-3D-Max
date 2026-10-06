@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Pokedex 3D Max - Windows Setup

echo ============================================================
echo              Pokedex 3D Max - Windows Setup
echo ============================================================
echo.
echo WINDOWS-ONLY MODE
echo.
echo This setup will:
echo   1. Check/download JDK 22
echo   2. Check/download Gradle
echo   3. Check Python
echo   4. Download/update every offline 3D model
echo   5. Build Pokedex-3D-Max-Windows.exe
echo.
echo Android/APK setup is disabled for now.
echo.
echo Live progress will stay visible in this window.
echo The same output is also saved to setup-all.log.
echo Existing model files are reused.
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

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_all.ps1"
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