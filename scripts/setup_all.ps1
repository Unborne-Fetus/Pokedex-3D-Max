param(
    [switch]$SkipModels,
    [switch]$SkipAndroidInstall,
    [switch]$SkipWindowsInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $RepoRoot ".tools"
$DistDir = Join-Path $RepoRoot "dist"
$GradleVersion = "9.6.0"
$JdkMajor = "22"
$AndroidApi = "36"
$AndroidBuildTools = "36.0.0"
$PackageName = "com.unbornefetus.pokedex3dmax"

function Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function EnsureDir([string]$Path) {
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

function DownloadFile([string]$Url, [string]$OutFile) {
    EnsureDir (Split-Path -Parent $OutFile)
    Write-Host "Downloading $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile
}

function ExpandFresh([string]$Zip, [string]$Destination) {
    if (Test-Path $Destination) {
        Remove-Item -Recurse -Force $Destination
    }
    EnsureDir $Destination
    Expand-Archive -Path $Zip -DestinationPath $Destination -Force
}

function BootstrapJdk {
    Step "Bootstrapping JDK $JdkMajor"
    $Root = Join-Path $ToolsDir ("jdk-" + $JdkMajor)
    $Marker = Join-Path $Root ".ready"

    if (-not (Test-Path $Marker)) {
        $Zip = Join-Path $ToolsDir "jdk.zip"
        $Url = "https://api.adoptium.net/v3/binary/latest/" + $JdkMajor + "/ga/windows/x64/jdk/hotspot/normal/eclipse"
        DownloadFile $Url $Zip
        ExpandFresh $Zip $Root
        Remove-Item -Force $Zip
        New-Item -ItemType File -Force -Path $Marker | Out-Null
    }

    $Java = Get-ChildItem $Root -Filter java.exe -File -Recurse | Where-Object { $_.FullName -match "\\bin\\java\.exe$" } | Select-Object -First 1
    if (-not $Java) {
        throw "Could not locate java.exe after JDK setup."
    }

    $env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $Java.FullName)
    $env:Path = (Join-Path $env:JAVA_HOME "bin") + ";" + $env:Path
    & java -version
}

function BootstrapGradle {
    Step "Bootstrapping Gradle $GradleVersion"
    $Root = Join-Path $ToolsDir ("gradle-" + $GradleVersion)
    $GradleBat = Join-Path $Root "bin\gradle.bat"

    if (-not (Test-Path $GradleBat)) {
        $Zip = Join-Path $ToolsDir "gradle.zip"
        $Temp = Join-Path $ToolsDir "gradle-extract"
        $Url = "https://services.gradle.org/distributions/gradle-" + $GradleVersion + "-bin.zip"

        DownloadFile $Url $Zip
        ExpandFresh $Zip $Temp
        Remove-Item -Force $Zip

        $Folder = Get-ChildItem $Temp -Directory | Select-Object -First 1
        if (-not $Folder) {
            throw "Gradle archive was invalid."
        }

        if (Test-Path $Root) {
            Remove-Item -Recurse -Force $Root
        }

        Move-Item $Folder.FullName $Root
        Remove-Item -Recurse -Force $Temp
    }

    return $GradleBat
}

function BootstrapAndroidSdk {
    Step "Bootstrapping Android SDK"
    $Sdk = Join-Path $ToolsDir "android-sdk"
    $Latest = Join-Path $Sdk "cmdline-tools\latest"
    $SdkManager = Join-Path $Latest "bin\sdkmanager.bat"

    if (-not (Test-Path $SdkManager)) {
        $Zip = Join-Path $ToolsDir "android-commandline-tools.zip"
        $Temp = Join-Path $ToolsDir "android-commandline-tools-extract"
        $Url = "https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip"

        DownloadFile $Url $Zip
        ExpandFresh $Zip $Temp
        Remove-Item -Force $Zip
        EnsureDir (Split-Path -Parent $Latest)

        $Source = Join-Path $Temp "cmdline-tools"
        if (-not (Test-Path $Source)) {
            $Source = $Temp
        }

        if (Test-Path $Latest) {
            Remove-Item -Recurse -Force $Latest
        }

        Move-Item $Source $Latest

        if (Test-Path $Temp) {
            Remove-Item -Recurse -Force $Temp
        }
    }

    $env:ANDROID_HOME = $Sdk
    $env:ANDROID_SDK_ROOT = $Sdk
    $env:Path = (Join-Path $Sdk "platform-tools") + ";" + $env:Path

    $Yes = (1..100 | ForEach-Object { "y" }) -join [Environment]::NewLine
    $Yes | & $SdkManager --sdk_root="$Sdk" --licenses | Out-Host

    & $SdkManager --sdk_root="$Sdk" "platform-tools" ("platforms;android-" + $AndroidApi) ("build-tools;" + $AndroidBuildTools)

    if ($LASTEXITCODE -ne 0) {
        throw "Android SDK package installation failed."
    }

    $SdkEscaped = $Sdk.Replace("\", "\\")
    Set-Content -Path (Join-Path $RepoRoot "local.properties") -Value ("sdk.dir=" + $SdkEscaped) -Encoding ASCII

    return $Sdk
}

function EnsurePython {
    Step "Checking Python"

    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python --version
        return "python"
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 --version
        return "py"
    }

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python is missing and winget is unavailable. Install Python 3.12, then rerun setup-all.bat."
    }

    & winget install --id Python.Python.3.12 --exact --silent --accept-source-agreements --accept-package-agreements

    if ($LASTEXITCODE -ne 0) {
        throw "Python installation failed."
    }

    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")

    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }

    throw "Python installed but is not visible yet. Close this window, reopen it, and run setup-all.bat again."
}

function InstallModels([string]$PythonCommand) {
    if ($SkipModels) {
        return $null
    }

    Step "Downloading/updating all offline 3D models"
    $Pack = Join-Path $env:LOCALAPPDATA "Pokedex3DMax\offline-models"
    EnsureDir $Pack
    $Script = Join-Path $RepoRoot "scripts\download_models.py"

    if ($PythonCommand -eq "py") {
        & py -3 $Script --target $Pack --workers 12
    } else {
        & python $Script --target $Pack --workers 12
    }

    if ($LASTEXITCODE -notin @(0,2)) {
        throw "Model-pack download failed."
    }

    if (-not (Test-Path (Join-Path $Pack "pack_info.json"))) {
        throw "Model pack did not finish correctly."
    }

    Get-Content (Join-Path $Pack "pack_info.json") | Out-Host
    return $Pack
}

function BuildEverything([string]$GradleBat) {
    Push-Location $RepoRoot

    try {
        Step "Building Android APK"
        & $GradleBat --no-daemon --non-interactive :app:assembleDebug
        if ($LASTEXITCODE -ne 0) {
            throw "Android build failed."
        }

        Step "Building Windows EXE and MSI"
        & $GradleBat --no-daemon --non-interactive :desktopApp:packageExe :desktopApp:packageMsi
        if ($LASTEXITCODE -ne 0) {
            throw "Windows build failed."
        }
    }
    finally {
        Pop-Location
    }
}

function CollectOutputs {
    Step "Collecting outputs"
    EnsureDir $DistDir
    Get-ChildItem $DistDir -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    $ApkSource = Join-Path $RepoRoot "app\build\outputs\apk\debug\app-debug.apk"
    if (-not (Test-Path $ApkSource)) {
        throw "Android APK was not found."
    }

    $Apk = Join-Path $DistDir "Pokedex-3D-Max-Android.apk"
    Copy-Item $ApkSource $Apk -Force

    $ExeSource = Get-ChildItem (Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\exe") -Filter *.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    $MsiSource = Get-ChildItem (Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\msi") -Filter *.msi -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1

    if (-not $ExeSource -and -not $MsiSource) {
        throw "Windows installer output was not found."
    }

    $Exe = $null
    $Msi = $null

    if ($ExeSource) {
        $Exe = Join-Path $DistDir "Pokedex-3D-Max-Windows.exe"
        Copy-Item $ExeSource.FullName $Exe -Force
    }

    if ($MsiSource) {
        $Msi = Join-Path $DistDir "Pokedex-3D-Max-Windows.msi"
        Copy-Item $MsiSource.FullName $Msi -Force
    }

    return @{ Apk=$Apk; Exe=$Exe; Msi=$Msi }
}

function InstallWindowsApp($Outputs) {
    if ($SkipWindowsInstall) {
        return
    }

    Step "Installing Windows app"

    if ($Outputs.Msi -and (Test-Path $Outputs.Msi)) {
        & msiexec.exe /i $Outputs.Msi /qn /norestart
        if ($LASTEXITCODE -notin @(0,3010)) {
            throw "Windows MSI installation failed."
        }
    }
    elseif ($Outputs.Exe) {
        Write-Host "MSI was not generated; the Windows EXE is ready in dist."
    }
}

function InstallAndroidDevice($Outputs,[string]$Pack) {
    if ($SkipAndroidInstall) {
        return
    }

    $Adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
    if (-not (Test-Path $Adb)) {
        return
    }

    Step "Checking for connected Android device"
    & $Adb start-server | Out-Null

    $Devices = @(& $Adb devices) | Select-Object -Skip 1 | Where-Object { $_ -match "\sdevice$" }

    if ($Devices.Count -eq 0) {
        Write-Host "No authorized Android device found. APK is ready in dist."
        return
    }

    & $Adb install -r $Outputs.Apk

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "APK installation failed. The APK is still available in dist."
        return
    }

    if (-not $Pack) {
        return
    }

    Step "Copying offline model pack to Android"
    $Remote = "/sdcard/Android/data/" + $PackageName + "/files/offline-models"
    & $Adb shell "mkdir -p '$Remote'" | Out-Null
    & $Adb push ($Pack + "\.") ($Remote + "/")

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Android blocked direct ADB access to the model directory."
        Write-Warning "The APK is installed and can still use online models."
    }
}

Write-Host "============================================================"
Write-Host "        Pokedex 3D Max - One Click Full Setup"
Write-Host "============================================================"

EnsureDir $ToolsDir
EnsureDir $DistDir

BootstrapJdk
$Gradle = BootstrapGradle
$Sdk = BootstrapAndroidSdk
$Python = EnsurePython
$Pack = InstallModels $Python
BuildEverything $Gradle
$Outputs = CollectOutputs
InstallWindowsApp $Outputs
InstallAndroidDevice $Outputs $Pack

Step "Finished"
Write-Host "Android APK: $($Outputs.Apk)"
if ($Outputs.Exe) { Write-Host "Windows EXE: $($Outputs.Exe)" }
if ($Outputs.Msi) { Write-Host "Windows MSI: $($Outputs.Msi)" }
if ($Pack) { Write-Host "Offline models: $Pack" }
Write-Host ""
Write-Host "Pokedex 3D Max setup is complete."
