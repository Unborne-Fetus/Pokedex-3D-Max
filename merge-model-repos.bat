@echo off
setlocal
cd /d "%~dp0"
where git >nul 2>nul || (echo Git for Windows is required. & pause & exit /b 1)
where python >nul 2>nul || (echo Python is required. & pause & exit /b 1)
echo Copying the original Switch model repository into Pokedex 3D Max...
if not exist ".cache\original-switch-models\.git" (
  git clone --depth 1 https://github.com/Unborne-Fetus/Pokedex-3D-Models-Animations.git ".cache\original-switch-models" || goto failed
) else (
  git -C ".cache\original-switch-models" pull --ff-only || goto failed
)
if not exist "web\models\switch" mkdir "web\models\switch"
for /d %%D in (".cache\original-switch-models\????") do (
  if exist "%%~fD\regular.glb" (
    if not exist "web\models\switch\%%~nxD" mkdir "web\models\switch\%%~nxD"
    copy /y "%%~fD\regular.glb" "web\models\switch\%%~nxD\regular.glb" >nul || goto failed
  )
)
python scripts\build_merged_switch_manifest.py || goto failed
git add web/models/switch web/models/switch-manifest.js web/models/switch-manifest.json
git commit -m "Merge original Switch models into Pokedex 3D Max"
git push origin main || goto failed
echo Complete. The model backup repository remains untouched.
pause
exit /b 0
:failed
echo Merge incomplete. Original repository remains untouched.
pause
exit /b 1
