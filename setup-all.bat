@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LOG=%~dp0setup-all.log"
>"%LOG%" echo Pokedex 3D Max setup log

echo ============================================================
echo              Pokedex 3D Max - Setup Everything
echo ============================================================
echo.
echo This one-click setup will bootstrap tools, download all models,
echo build the Android APK and Windows app, then install what it can.
echo.

if not exist "%~dp0scripts\setup_all.ps1" (
  echo ERROR: scripts\setup_all.ps1 is missing.
  echo Run: git pull
  echo Then run setup-all.bat again.
  echo.
  pause
  exit /b 2
)

echo Starting PowerShell setup...
echo Output is being written to:
echo   %LOG%
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_all.ps1" >> "%LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

echo.
echo ============================================================
if "%EXITCODE%"=="0" (
  echo Setup finished successfully.
  echo Check the dist folder for the APK and Windows installers.
) else (
  echo Setup stopped with error code %EXITCODE%.
  echo.
  echo Last setup output:
  echo ------------------------------------------------------------
  powershell.exe -NoProfile -Command "Get-Content -Path '%LOG%' -Tail 60"
  echo ------------------------------------------------------------
  echo.
  echo Full log:
  echo   %LOG%
)
echo ============================================================
echo.
pause
exit /b %EXITCODE%