@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python is required. Use setup-all.bat to install the project dependencies.
        pause
        exit /b 2
    )
    set "PYTHON=python"
)

echo Recovering Caterpie, Metapod and Butterfree from the existing Switch release...
echo This checks only the first 100-model shard and will not replace other Pokemon.
%PYTHON% -u scripts\remote_model_pack.py install --dex 10 --dex 11 --dex 12 --source-game swsh
if errorlevel 1 (
    echo.
    echo They are not all available as verified Sword/Shield models in the release.
    echo Trying already downloaded original Sword/Shield archives instead...
    %PYTHON% -u scripts\import_switch_game_assets.py --game swsh --dex 10 --dex 11 --dex 12
    if errorlevel 1 (
        echo.
        echo Recovery is incomplete. Provide your existing Sword/Shield model,
        echo matching animation, and texture archives under switch-assets.
        echo No existing models were removed.
        pause
        exit /b 2
    )
)

set "MISSING=0"
for %%N in (0010 0011 0012) do (
    if not exist "web\models\switch\%%N\regular.glb" (
        echo Missing verified model %%N after recovery.
        set "MISSING=1"
    )
)
if "%MISSING%"=="1" (
    echo The website has not been changed to pretend missing models exist.
    pause
    exit /b 2
)

echo.
echo Recovered all three models in web\models\switch.
echo Review each model and its animations, then commit the three GLBs
echo and web\models\switch-manifest.js/json to GitHub to update the site.
echo The Finished Pokemon bar is unchanged until they are reviewed.
pause
exit /b 0
