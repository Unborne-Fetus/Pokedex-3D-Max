@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Import PokeMiners Models

echo ============================================================
echo        Pokedex 3D Max - Import PokeMiners Models
echo ============================================================
echo.
echo This will:
echo   1. Sparse-fetch only PokeMiners 3D Pokemon assets
echo   2. Find all pm####_##_Rig FBX folders
echo   3. Convert them to web-ready GLB files with Blender
echo   4. Preserve embedded rigs/animations/materials where possible
echo   5. Generate a local override manifest for the web viewer
echo.
echo Existing converted models are reused, so reruns resume.
echo Generated models are intentionally ignored by Git.
echo.
pause

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python was not found.
    echo Run setup-all.bat first or install Python 3.
    echo.
    pause
    exit /b 1
  )
  py -3 scripts\import_pokeminers.py --update
) else (
  python scripts\import_pokeminers.py --update
)

set "EXITCODE=%ERRORLEVEL%"
echo.
if "%EXITCODE%"=="0" (
  echo ============================================================
  echo PokeMiners import finished.
  echo Open index.html and hard-refresh the browser.
  echo ============================================================
) else (
  echo ============================================================
  echo Import stopped with error code %EXITCODE%.
  echo ============================================================
)
echo.
pause
exit /b %EXITCODE%