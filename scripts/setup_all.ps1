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

    # Missing Python modules write a traceback to stderr. With the script-wide
    # ErrorActionPreference set to Stop, Windows PowerShell can terminate here
    # before setup gets a chance to install Pillow. Probe native Python with
    # non-terminating error handling and inspect its exit code instead.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Command -eq "py") {
            & py -3 -c "import PIL" *> $null
            $PillowCheckExitCode = $LASTEXITCODE
        } else {
            & python -c "import PIL" *> $null
            $PillowCheckExitCode = $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }

    if ($PillowCheckExitCode -ne 0) {
        Stamp "Pillow is not installed. Installing it now..."

        $PreviousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            if ($Command -eq "py") {
                & py -3 -m pip install --disable-pip-version-check Pillow
                $PillowInstallExitCode = $LASTEXITCODE
            } else {
                & python -m pip install --disable-pip-version-check Pillow
                $PillowInstallExitCode = $LASTEXITCODE
            }
        } finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }

        if ($PillowInstallExitCode -ne 0) {
            throw "Pillow installation failed. Install Pillow with pip and rerun setup-all.bat."
        }

        $PreviousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try {
            if ($Command -eq "py") {
                & py -3 -c "import PIL; print(PIL.__version__)"
                $PillowVerifyExitCode = $LASTEXITCODE
            } else {
                & python -c "import PIL; print(PIL.__version__)"
                $PillowVerifyExitCode = $LASTEXITCODE
            }
        } finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }

        if ($PillowVerifyExitCode -ne 0) {
            throw "Pillow was installed but Python still cannot import it."
        }
    } else {
        Stamp "Pillow is already installed."
    }

    Stamp "Pillow is ready."
    return $Command
}

function InstallModels([string]$PythonCommand) {
    Step "STEP 4/5 - Preparing offline 3D model pack"
    $Pack = Join-Path $env:LOCALAPPDATA "Pokedex3DMax\offline-models"

    if ($SkipModels) {
        if (Test-Path $Pack) {
            Stamp "Fast mode: skipping model sync and reusing the existing offline model folder."
            return $Pack
        }
        Stamp "Fast mode: skipping the optional offline model download."
        Stamp "The app can use its online/CDN model sources instead."
        return $null
    }

    EnsureDir $Pack
    $Info = Join-Path $Pack "pack_info.json"

    if ((-not $RefreshModels) -and (Test-Path $Info)) {
        try {
            $PackInfo = Get-Content $Info -Raw | ConvertFrom-Json
            if (($PackInfo.modelCount -gt 0) -and ($PackInfo.failedCount -eq 0)) {
                Stamp ("Offline model pack is already complete (" + $PackInfo.modelCount + " models).")
                Stamp "Skipping network scan/download. Use -RefreshModels to force a refresh."
                return $Pack
            }
        } catch {
            Stamp "Existing pack_info.json could not be validated; continuing with model sync."
        }
    }

    $Script = Join-Path $RepoRoot "scripts\download_models.py"
    $Workers = [Math]::Min(24, [Math]::Max(8, [Environment]::ProcessorCount * 2))

    Stamp ("Model folder: " + $Pack)
    Stamp ("Using " + $Workers + " parallel model download workers.")
    Stamp "Existing files are reused; only missing/changed files need network work."

    $env:PYTHONUNBUFFERED = "1"
    if ($PythonCommand -eq "py") {
        & py -3 -u $Script --target $Pack --workers $Workers
    } else {
        & python -u $Script --target $Pack --workers $Workers
    }

    if ($LASTEXITCODE -notin @(0,2)) { throw "Model-pack download failed." }
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