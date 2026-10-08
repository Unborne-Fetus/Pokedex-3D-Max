@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Pokedex 3D Max - Publish Model Pack

echo ============================================================
echo       Pokedex 3D Max - Publish Switch Model Pack
echo ============================================================
echo.
echo This packages the validated converted GLBs into versioned
echo release shards. Your downloaded source archives are untouched.
echo.
echo Only publish assets where you have permission to distribute them.
echo.
pause

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\publish_model_pack.ps1"
set "EXITCODE=%ERRORLEVEL%"

echo.
if "%EXITCODE%"=="0" (
  echo Model pack publish completed successfully.
) else (
  echo Model pack publish failed with error code %EXITCODE%.
)
echo.
pause
exit /b %EXITCODE%
