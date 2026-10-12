@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Import GFPAK Pokemon

echo ============================================================
echo       Import GFPAK Pokemon ZIP - Blender not required
echo ============================================================
echo.
set "SOURCE=%~1"
if not defined SOURCE (
  echo Choose a ZIP exported using GFPAK Open's Export Pokemon button.
  for /f "usebackq delims=" %%F in (`powershell.exe -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='GFPAK Pokemon ZIP (*.zip)|*.zip'; if($d.ShowDialog() -eq 'OK') {$d.FileName}"`) do set "SOURCE=%%F"
)
if not defined SOURCE (
  echo No ZIP selected.
  pause
  exit /b 1
)
if not exist "%SOURCE%" (
  echo ZIP not found: %SOURCE%
  pause
  exit /b 2
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -u scripts\import_gfpak_zip.py "%SOURCE%" %2 %3 %4 %5
) else (
  python -u scripts\import_gfpak_zip.py "%SOURCE%" %2 %3 %4 %5
)
set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
  echo Import succeeded. Refresh Pokedex 3D Max to see the model.
) else (
  echo Import failed. Check the message above; existing models were not intentionally replaced.
  echo Use --game sv, --game za, etc. if GFPAK couldn't identify the source game.
  echo Use --replace only if you explicitly want to overwrite an existing model.
)
echo.
pause
exit /b %EXITCODE%
