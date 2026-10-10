@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Missing Switch Models 1-100
echo ============================================================
echo     Pokedex 3D Max - Missing Models 1-100
echo ============================================================
echo.
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -u "scripts\recover_missing_switch_models.py" --batch 1 %*
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python 3 is required. Install dependencies with setup-all.bat.
        pause
        exit /b 2
    )
    python -u "scripts\recover_missing_switch_models.py" --batch 1 %*
)
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
    echo Some models are still missing or failed validation.
    echo See .cache\missing-model-batches\batch-1.json for the exact list.
) else (
    echo All requested models in this batch passed structural checks.
)
echo.
pause
exit /b %RESULT%
