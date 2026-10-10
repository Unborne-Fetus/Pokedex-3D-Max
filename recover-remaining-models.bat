@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Pokedex 3D Max - Recover Remaining Models
echo ============================================================
echo          Pokedex 3D Max - Remaining Model Recovery
echo ============================================================
echo.
if not exist "scripts\import_switch_game_assets.py" (
  echo ERROR: Put this BAT in the Pokedex-3D-Max repository root.
  goto :failed
)
if not exist ".cache\remaining-model-diagnosis\report.json" (
  echo ERROR: Diagnosis report not found. Run diagnose-remaining-models.bat first.
  goto :failed
)
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_LAUNCHER=py"
  set "PYTHON_ARG=-3"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python 3 is required.
    goto :failed
  )
  set "PYTHON_LAUNCHER=python"
  set "PYTHON_ARG="
)
echo Checking Blender...
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\ensure_recovery_blender.ps1"
if errorlevel 1 (
  echo ERROR: Could not prepare Blender. Check your internet connection and disk space.
  goto :failed
)
set /p "BLENDER=" < ".cache\remaining-model-diagnosis\blender-path.txt"
echo Reading the latest diagnosis and converting only regular model candidates...
echo Existing valid models will not be force-reconverted.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop'; $r=Get-Content -LiteralPath '.cache\remaining-model-diagnosis\report.json' -Raw | ConvertFrom-Json; $targets=@($r.pokemon | Where-Object { $_.status -eq 'ready_to_attempt_conversion' -and $_.installedValid -ne $true } | ForEach-Object { [int]$_.dex } | Sort-Object -Unique); $others=@($r.pokemon | Where-Object { $_.status -eq 'only_other_forms_found' }); $absent=@($r.pokemon | Where-Object { $_.status -eq 'regular_model_not_found_in_sources' }); Write-Host ('Conversion-ready: '+$targets.Count+' / Alternate forms only: '+$others.Count+' / Source missing: '+$absent.Count); if ($targets.Count -eq 0) { Write-Host 'No regular models are ready to convert.'; exit 0 }; $a=@(); if ($env:PYTHON_ARG) { $a+= $env:PYTHON_ARG }; $a+=@('-u','scripts\import_switch_game_assets.py'); foreach($d in $targets){ $a+='--dex'; $a+=[string]$d }; & $env:PYTHON_LAUNCHER @a; exit $LASTEXITCODE"
set "RESULT=%ERRORLEVEL%"
echo.
echo Rechecking installed models and remaining source candidates...
if defined PYTHON_ARG (
  "%PYTHON_LAUNCHER%" %PYTHON_ARG% -u scripts\diagnose_remaining_switch_models.py
) else (
  "%PYTHON_LAUNCHER%" -u scripts\diagnose_remaining_switch_models.py
)
echo.
echo ============================================================
echo Conversion exit code: %RESULT%
echo Updated report: .cache\remaining-model-diagnosis\report.tsv
echo Review imported models visually before marking them finished.
echo Alternate-form-only and missing-source entries require separate work.
echo ============================================================
pause
exit /b %RESULT%
:failed
echo.
pause
exit /b 1
