@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo              Pokedex 3D Max - Setup Everything
echo ============================================================
echo.
echo This one-click setup will bootstrap tools, download all models,
echo build the Android APK and Windows app, then install what it can.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_all.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
  echo Setup finished successfully.
  echo Check the dist folder for the APK and Windows installers.
) else (
  echo Setup stopped with error code %EXITCODE%.
)
echo.
pause
exit /b %EXITCODE%