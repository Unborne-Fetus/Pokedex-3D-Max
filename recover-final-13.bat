@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Recover Final 13 Original Models
echo ============================================================
echo        Recover Final 13 Original Switch Models
echo ============================================================
echo.
echo Only the 13 remaining Pokemon will be targeted.
echo Existing Switch models will not be replaced for other Pokemon.
echo.
rem With no file arguments, use setup's targeted MEGA discovery and only
rem download SV + SwSh Gen8 source packs. Dropped archives run directly.
if "%~1"=="" (
    call "%~dp0setup-all.bat" final13
    exit /b %ERRORLEVEL%
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -u "scripts\recover_final_13.py" %*
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3 was not found. Run setup-all.bat to install dependencies.
        pause
        exit /b 2
    )
    python -u "scripts\recover_final_13.py" %*
)
set "RESULT=%ERRORLEVEL%"
echo.
echo Final report: .cache\final-13-recovery\report.tsv
if not "%RESULT%"=="0" echo The original sources and conversion still need attention for some Pokemon.
echo.
pause
exit /b %RESULT%
