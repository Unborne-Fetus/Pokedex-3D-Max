param(
    [switch]$SkipModels,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $RepoRoot ".tools"
$DistDir = Join-Path $RepoRoot "dist"
$LogFile = Join-Path $RepoRoot "setup-all.log"
$GradleVersion = "9.6.0"
$JdkMajor = "22"

function Stamp([string]$Text) {
    $Now = Get-Date -Format "HH:mm:ss"
    Write-Host ("[" + $Now + "] " + $Text)
}

function Step([string]$Text) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor DarkGray
    Stamp $Text
    Write-Host "============================================================" -ForegroundColor DarkGray
}

function EnsureDir([string]$Path) {
    if (-not (Test-Path $Path)) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
}

function DownloadFile([string]$Url, [string]$OutFile) {
    EnsureDir (Split-Path -Parent $OutFile)
    Stamp ("Downloading " + $Url)
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile
    Stamp ("Downloaded " + $OutFile)
}

function ExpandFresh([string]$Zip, [string]$Destination) {
    Stamp ("Extracting " + $Zip)
    if (Test-Path $Destination) { Remove-Item -Recurse -Force $Destination }
    EnsureDir $Destination
    Expand-Archive -Path $Zip -DestinationPath $Destination -Force
    Stamp "Extraction complete."
}

function BootstrapJdk {
    Step "STEP 1/5 - Checking JDK 22"
    $Root = Join-Path $ToolsDir ("jdk-" + $JdkMajor)
    $Marker = Join-Path $Root ".ready"

    if (-not (Test-Path $Marker)) {
        Stamp "JDK 22 is not cached. Downloading it now."
        $Zip = Join-Path $ToolsDir "jdk.zip"
        $Url = "https://api.adoptium.net/v3/binary/latest/" + $JdkMajor + "/ga/windows/x64/jdk/hotspot/normal/eclipse"
        DownloadFile $Url $Zip
        ExpandFresh $Zip $Root
        Remove-Item -Force $Zip
        New-Item -ItemType File -Force -Path $Marker | Out-Null
    } else {
        Stamp "JDK 22 already exists. Reusing it."
    }

    $Java = Get-ChildItem $Root -Filter java.exe -File -Recurse | Where-Object { $_.FullName -match "\\bin\\java\.exe$" } | Select-Object -First 1
    if (-not $Java) { throw "Could not locate java.exe after JDK setup." }
    $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $Java.FullName)
    $env:Path = (Join-Path $env:JAVA_HOME "bin") + ";" + $env:Path
    Stamp ("JAVA_HOME = " + $env:JAVA_HOME)
    & java -version
}

function BootstrapGradle {
    Step "STEP 2/5 - Checking Gradle"
    $Root = Join-Path $ToolsDir ("gradle-" + $GradleVersion)
    $GradleBat = Join-Path $Root "bin\gradle.bat"

    if (-not (Test-Path $GradleBat)) {
        Stamp ("Gradle " + $GradleVersion + " is not cached. Downloading it now.")
        $Zip = Join-Path $ToolsDir "gradle.zip"
        $Temp = Join-Path $ToolsDir "gradle-extract"
        $Url = "https://services.gradle.org/distributions/gradle-" + $GradleVersion + "-bin.zip"
        DownloadFile $Url $Zip
        ExpandFresh $Zip $Temp
        Remove-Item -Force $Zip
        $Folder = Get-ChildItem $Temp -Directory | Select-Object -First 1
        if (-not $Folder) { throw "Gradle archive was invalid." }
        if (Test-Path $Root) { Remove-Item -Recurse -Force $Root }
        Move-Item $Folder.FullName $Root
        Remove-Item -Recurse -Force $Temp
    } else {
        Stamp ("Gradle " + $GradleVersion + " already exists. Reusing it.")
    }

    Stamp ("Gradle executable = " + $GradleBat)
    return $GradleBat
}

function EnsurePython {
    Step "STEP 3/5 - Checking Python"
    $Command = $null
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $Version = (& python --version 2>&1)
        Stamp ("Found " + $Version)
        $Command = "python"
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $Version = (& py -3 --version 2>&1)
        Stamp ("Found " + $Version)
        $Command = "py"
    } else {
        Stamp "Python was not found."
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "Python is missing and winget is unavailable. Install Python 3.12, then run setup-all.bat again."
        }
        Stamp "Installing Python 3.12 with winget..."
        & winget install --id Python.Python.3.12 --exact --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "Python installation failed." }
        $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
        if (Get-Command python -ErrorAction SilentlyContinue) { $Command = "python" }
        elseif (Get-Command py -ErrorAction SilentlyContinue) { $Command = "py" }
        else { throw "Python installed but is not visible yet. Close this window and run setup-all.bat again." }
    }

    Stamp "Checking Pillow for WebP-to-PNG model conversion..."
    if ($Command -eq "py") {
        & py -3 -c "import PIL" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Stamp "Installing Pillow..."
            & py -3 -m pip install --disable-pip-version-check --quiet Pillow
            if ($LASTEXITCODE -ne 0) { throw "Pillow installation failed." }
        }
    } else {
        & python -c "import PIL" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Stamp "Installing Pillow..."
            & python -m pip install --disable-pip-version-check --quiet Pillow
            if ($LASTEXITCODE -ne 0) { throw "Pillow installation failed." }
        }
    }
    Stamp "Pillow is ready."
    return $Command
}

function InstallModels([string]$PythonCommand) {
    Step "STEP 4/5 - Preparing complete offline 3D model pack"
    if ($SkipModels) {
        Stamp "Skipping model download because -SkipModels was supplied."
        return $null
    }

    $Pack = Join-Path $env:LOCALAPPDATA "Pokedex3DMax\offline-models"
    EnsureDir $Pack
    $Script = Join-Path $RepoRoot "scripts\download_models.py"
    Stamp ("Model folder: " + $Pack)
    Stamp "The downloader will print progress continuously."
    Stamp "Existing model files are reused, so rerunning setup does not start over."

    $env:PYTHONUNBUFFERED = "1"
    if ($PythonCommand -eq "py") {
        & py -3 -u $Script --target $Pack --workers 12
    } else {
        & python -u $Script --target $Pack --workers 12
    }

    if ($LASTEXITCODE -notin @(0,2)) { throw "Model-pack download failed." }
    $Info = Join-Path $Pack "pack_info.json"
    if (-not (Test-Path $Info)) { throw "Model pack did not produce pack_info.json." }
    Stamp "Model pack summary:"
    Get-Content $Info | Out-Host
    return $Pack
}

function BuildWindows([string]$GradleBat) {
    Step "STEP 5/5 - Building Windows EXE"
    Push-Location $RepoRoot
    try {
        Stamp "Starting Gradle desktop build. Gradle output will remain visible."
        & $GradleBat --console=plain --no-daemon :desktopApp:packageExe
        if ($LASTEXITCODE -ne 0) { throw "Windows EXE build failed." }
    } finally {
        Pop-Location
    }
    Stamp "Gradle build completed."
}

function CollectExe {
    Step "Collecting final EXE"
    EnsureDir $DistDir
    $ExeSource = Get-ChildItem (Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\exe") -Filter *.exe -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $ExeSource) { throw "Windows EXE output was not found after a successful Gradle build." }
    $Exe = Join-Path $DistDir "Pokedex-3D-Max-Windows.exe"
    Copy-Item $ExeSource.FullName $Exe -Force
    Stamp ("Final EXE: " + $Exe)
    Stamp ("Size: " + [math]::Round((Get-Item $Exe).Length / 1MB, 1).ToString() + " MB")
    return $Exe
}

function InstallExe([string]$Exe) {
    if ($SkipInstall) {
        Stamp "Skipping installer launch because -SkipInstall was supplied."
        return
    }
    Write-Host ""
    $Answer = Read-Host "Build finished. Launch the Windows installer now? (Y/n)"
    if ([string]::IsNullOrWhiteSpace($Answer) -or $Answer.ToLowerInvariant() -eq "y") {
        Stamp "Launching Windows installer..."
        Start-Process -FilePath $Exe
    } else {
        Stamp "Installer was not launched. The EXE is ready in dist."
    }
}

EnsureDir $ToolsDir
EnsureDir $DistDir

try {
    Start-Transcript -Path $LogFile -Force | Out-Null
    Write-Host "============================================================"
    Write-Host "        Pokedex 3D Max - Windows Setup"
    Write-Host "============================================================"
    Stamp "Windows-only mode: Android/APK steps are disabled."
    Stamp "Nothing is frozen if timestamps keep appearing or a download/build counter changes."
    Stamp ("Log file: " + $LogFile)

    BootstrapJdk
    $Gradle = BootstrapGradle
    $Python = EnsurePython
    $Pack = InstallModels $Python
    BuildWindows $Gradle
    $Exe = CollectExe

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Stamp "SUCCESS - Windows build is ready."
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ("EXE: " + $Exe)
    if ($Pack) { Write-Host ("Offline models: " + $Pack) }
    InstallExe $Exe
} catch {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Red
    Stamp "SETUP FAILED"
    Write-Host "============================================================" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host ("Full log: " + $LogFile)
    exit 1
} finally {
    try { Stop-Transcript | Out-Null } catch {}
}