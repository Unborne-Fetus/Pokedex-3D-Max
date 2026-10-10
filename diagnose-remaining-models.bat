@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Diagnose 122 Remaining Models
echo ============================================================
echo       Pokedex 3D Max - Remaining Model Diagnosis
echo ============================================================
echo.
echo This scans your existing Switch archives or extracted sources.
echo It does not overwrite any models, animations, or textures.
echo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -u "scripts\diagnose_remaining_switch_models.py" %*
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3 is required. Run setup-all.bat to install dependencies.
        pause
        exit /b 2
    )
    python -u "scripts\diagnose_remaining_switch_models.py" %*
)
set "RESULT=%ERRORLEVEL%"
echo.
echo Detailed results: .cache\remaining-model-diagnosis\report.tsv
echo.
if not "%RESULT%"=="0" (
    echo Some source archives could not be scanned. Review source issues above.
)
pause
exit /b %RESULT%
