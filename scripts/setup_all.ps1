param(
    [switch]$SkipModels,
    [switch]$SkipSwitchAssets,
    [switch]$RefreshModels,
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
$BlenderPortableVersion = "4.5.14"
$BlenderPortableUrl = "https://mirror.blender.org/release/Blender4.5/blender-4.5.14-windows-x64.zip"
$MegaFolderLink = "https://mega.nz/folder/elJhVC5D#NU-yzmXuTlsIIzXAMLKVaA"
$MegaAssetCache = Join-Path $RepoRoot ".cache\mega-switch-assets"
$MegaNoProgressTimeoutSeconds = 300
$MegaDownloadRetries = 3

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
    Step "STEP 1/7 - Checking JDK 22"
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
    Step "STEP 2/7 - Checking Gradle"
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
    Step "STEP 3/7 - Checking Python"
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

function EnsureBlender {
    Step "STEP 4/7 - Checking Blender"

    $Blender = $null
    if (Get-Command blender -ErrorAction SilentlyContinue) {
        $Blender = (Get-Command blender).Source
    }

    $BlenderRoot = Join-Path $env:ProgramFiles "Blender Foundation"
    if ((-not $Blender) -and (Test-Path $BlenderRoot)) {
        $Blender = Get-ChildItem $BlenderRoot -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }

    $PortableRoot = Join-Path $ToolsDir ("blender-" + $BlenderPortableVersion)
    $PortableExe = Get-ChildItem $PortableRoot -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if ((-not $Blender) -and $PortableExe) { $Blender = $PortableExe }

    if (-not $Blender) {
        Stamp ("Blender was not found. Downloading portable Blender " + $BlenderPortableVersion + "...")
        $Zip = Join-Path $ToolsDir ("blender-" + $BlenderPortableVersion + ".zip")
        if (-not (Test-Path $Zip)) {
            $Downloaded = $false
            if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
                $PreviousErrorActionPreference = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    & curl.exe -L --fail --retry 3 --retry-delay 2 -A "Mozilla/5.0" -o $Zip $BlenderPortableUrl
                    $Downloaded = ($LASTEXITCODE -eq 0 -and (Test-Path $Zip) -and ((Get-Item $Zip).Length -gt 100MB))
                } finally {
                    $ErrorActionPreference = $PreviousErrorActionPreference
                }
            }
            if (-not $Downloaded) {
                try {
                    DownloadFile $BlenderPortableUrl $Zip
                    $Downloaded = (Test-Path $Zip) -and ((Get-Item $Zip).Length -gt 100MB)
                } catch {
                    $Downloaded = $false
                }
            }
            if (-not $Downloaded) {
                if (Test-Path $Zip) { Remove-Item -Force $Zip }
                throw "Could not download portable Blender from the official Blender archive."
            }
        } else {
            Stamp "Portable Blender ZIP already exists. Reusing it."
        }

        if (Test-Path $PortableRoot) { Remove-Item -Recurse -Force $PortableRoot }
        ExpandFresh $Zip $PortableRoot
        $Blender = Get-ChildItem $PortableRoot -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if (-not $Blender) { throw "Portable Blender extracted but blender.exe was not found." }
    }

    Stamp ("Blender = " + $Blender)
    return $Blender
}

function EnsureSevenZip {
    if (Get-Command 7z -ErrorAction SilentlyContinue) { return (Get-Command 7z).Source }
    $Seven = Join-Path $env:ProgramFiles "7-Zip\7z.exe"
    if (Test-Path $Seven) {
        $env:Path = (Split-Path -Parent $Seven) + ";" + $env:Path
        return $Seven
    }
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Stamp "Installing 7-Zip for BDSP .7z extraction..."
        & winget install --id 7zip.7zip --exact --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -eq 0 -and (Test-Path $Seven)) {
            $env:Path = (Split-Path -Parent $Seven) + ";" + $env:Path
            return $Seven
        }
    }
    return $null
}

function FindMegaTool([string]$Name) {
    $CommandName = "mega-" + $Name
    if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
        return (Get-Command $CommandName).Source
    }
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA ("MEGAcmd\" + $CommandName + ".bat")),
        (Join-Path $env:LOCALAPPDATA ("MEGAcmd\" + $CommandName + ".exe")),
        (Join-Path $env:ProgramFiles ("MEGAcmd\" + $CommandName + ".bat")),
        (Join-Path $env:ProgramFiles ("MEGAcmd\" + $CommandName + ".exe"))
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) { return $Candidate }
    }
    return $null
}

function FindMegaGet {
    return FindMegaTool "get"
}

function EnsureMegaCmd {
    $MegaGet = FindMegaGet
    if ($MegaGet) {
        Stamp ("MEGAcmd = " + $MegaGet)
        return $MegaGet
    }

    Stamp "MEGAcmd was not found. Downloading the official installer directly..."
    $Installer = Join-Path $ToolsDir "MEGAcmdSetup64.exe"
    $MegaInstallerUrl = "https://mega.nz/MEGAcmdSetup64.exe"

    if (-not (Test-Path $Installer) -or (Get-Item $Installer).Length -lt 10MB) {
        if (Test-Path $Installer) { Remove-Item -Force $Installer }
        $Downloaded = $false
        if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
            $PreviousErrorActionPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & curl.exe -L --fail --retry 3 --retry-delay 2 -A "Mozilla/5.0" -o $Installer $MegaInstallerUrl
                $Downloaded = ($LASTEXITCODE -eq 0 -and (Test-Path $Installer) -and ((Get-Item $Installer).Length -gt 10MB))
            } finally {
                $ErrorActionPreference = $PreviousErrorActionPreference
            }
        }
        if (-not $Downloaded) { DownloadFile $MegaInstallerUrl $Installer }
    }

    Stamp "Installing MEGAcmd silently..."
    $Process = Start-Process -FilePath $Installer -ArgumentList "/S" -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw "MEGAcmd installer failed with exit code $($Process.ExitCode)." }

    $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
        [Environment]::GetEnvironmentVariable("Path","User") + ";" +
        (Join-Path $env:LOCALAPPDATA "MEGAcmd") + ";" +
        (Join-Path $env:ProgramFiles "MEGAcmd")

    Start-Sleep -Seconds 2
    $MegaGet = FindMegaGet
    if (-not $MegaGet) { throw "MEGAcmd installed, but mega-get could not be located." }
    Stamp ("MEGAcmd = " + $MegaGet)
    return $MegaGet
}

function InvokeMegaScriptable([string]$ToolPath, [string[]]$Arguments) {
    if ($ToolPath.ToLowerInvariant().EndsWith(".bat")) {
        $Quoted = @()
        foreach ($Arg in $Arguments) { $Quoted += ('"' + ($Arg -replace '"', '""') + '"') }
        $CmdLine = '/d /s /c ""' + $ToolPath + '" ' + ($Quoted -join " ") + '"'
        $Output = & cmd.exe $CmdLine 2>&1
        return @{ ExitCode = $LASTEXITCODE; Output = @($Output) }
    }
    $Output = & $ToolPath @Arguments 2>&1
    return @{ ExitCode = $LASTEXITCODE; Output = @($Output) }
}

function GetDirectoryBytes([string]$Path) {
    if (-not (Test-Path $Path)) { return [int64]0 }
    $Sum = (Get-ChildItem $Path -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    if ($null -eq $Sum) { return [int64]0 }
    return [int64]$Sum
}

function GetMegaDesiredRemoteArchives {
    [void](EnsureMegaCmd)
    $MegaLogin = FindMegaTool "login"
    $MegaFind = FindMegaTool "find"
    if (-not $MegaLogin -or -not $MegaFind) { throw "MEGAcmd login/find commands could not be located." }

    Stamp "Opening the shared MEGA folder in read-only mode..."
    $Login = InvokeMegaScriptable $MegaLogin @($MegaFolderLink, "--resume")
    if ($Login.ExitCode -ne 0) {
        $Login = InvokeMegaScriptable $MegaLogin @($MegaFolderLink)
    }
    if ($Login.ExitCode -ne 0) {
        throw ("Could not open the shared MEGA folder: " + (($Login.Output | Select-Object -Last 5) -join " "))
    }

    Stamp "Scanning MEGA metadata only; the full 14 GB folder will NOT be downloaded."
    $Found = InvokeMegaScriptable $MegaFind @("/", "--type=f", "--pattern=*.zip")
    $Found7z = InvokeMegaScriptable $MegaFind @("/", "--type=f", "--pattern=*.7z")
    $Lines = @($Found.Output) + @($Found7z.Output)

    $Selected = New-Object System.Collections.Generic.List[string]
    foreach ($Line in $Lines) {
        $Path = ([string]$Line).Trim()
        if (-not $Path -or $Path.StartsWith("[err:")) { continue }
        $Leaf = Split-Path $Path -Leaf
        if ($Leaf -match "(?i)(poke|pokemon)" -and
            $Leaf -match "(?i)(anim|pokeanim|model|poke|pokemon|dlc)" -and
            ($Leaf.EndsWith(".zip", [StringComparison]::OrdinalIgnoreCase) -or $Leaf.EndsWith(".7z", [StringComparison]::OrdinalIgnoreCase))) {
            if (-not $Selected.Contains($Path)) { $Selected.Add($Path) }
        }
    }

    if ($Selected.Count -eq 0) {
        throw "MEGA metadata scan succeeded, but no Pokemon model/animation archives matched."
    }

    Stamp ("Selected " + $Selected.Count + " Pokemon model/animation archive(s) instead of the whole folder.")
    foreach ($Path in $Selected) { Stamp ("  " + $Path) }
    return $Selected.ToArray()
}

function DownloadMegaArchiveWithWatchdog([string]$RemotePath) {
    EnsureDir $MegaAssetCache
    $MegaGet = EnsureMegaCmd
    $Leaf = Split-Path $RemotePath -Leaf

    $Existing = Get-ChildItem $MegaAssetCache -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $Leaf -and $_.Length -gt 1MB } | Select-Object -First 1
    if ($Existing) {
        Stamp ("Already downloaded: " + $Leaf)
        return
    }

    for ($Attempt = 1; $Attempt -le $MegaDownloadRetries; $Attempt++) {
        Stamp ("Downloading " + $Leaf + " (attempt " + $Attempt + "/" + $MegaDownloadRetries + ")...")
        $BeforeBytes = GetDirectoryBytes $MegaAssetCache
        $LastBytes = $BeforeBytes
        $LastProgress = Get-Date

        if ($MegaGet.ToLowerInvariant().EndsWith(".bat")) {
            $ArgLine = '/d /s /c ""' + $MegaGet + '" -m "' + $RemotePath + '" "' + $MegaAssetCache + '" "'
            $Proc = Start-Process -FilePath "cmd.exe" -ArgumentList $ArgLine -PassThru -NoNewWindow
        } else {
            $Proc = Start-Process -FilePath $MegaGet -ArgumentList @("-m", $RemotePath, $MegaAssetCache) -PassThru -NoNewWindow
        }

        while (-not $Proc.HasExited) {
            Start-Sleep -Seconds 10
            $Proc.Refresh()
            $NowBytes = GetDirectoryBytes $MegaAssetCache
            if ($NowBytes -gt $LastBytes) {
                $DeltaMB = [math]::Round(($NowBytes - $BeforeBytes) / 1MB, 1)
                Stamp ("  transfer active: +" + $DeltaMB + " MB this attempt")
                $LastBytes = $NowBytes
                $LastProgress = Get-Date
            } elseif (((Get-Date) - $LastProgress).TotalSeconds -ge $MegaNoProgressTimeoutSeconds) {
                Stamp ("  no disk progress for " + $MegaNoProgressTimeoutSeconds + " seconds; restarting this archive download.")
                try { Stop-Process -Id $Proc.Id -Force -ErrorAction SilentlyContinue } catch {}
                break
            }
        }

        $Existing = Get-ChildItem $MegaAssetCache -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq $Leaf -and $_.Length -gt 1MB } | Select-Object -First 1
        if ($Existing) {
            Stamp ("Completed: " + $Leaf + " (" + [math]::Round($Existing.Length / 1MB, 1) + " MB)")
            return
        }

        if ($Attempt -lt $MegaDownloadRetries) {
            Stamp "  retrying after 20 seconds; existing MEGA/cache data is preserved."
            Start-Sleep -Seconds 20
        }
    }

    throw ("Download repeatedly stalled for " + $Leaf + ". Setup stopped instead of hanging forever. Rerun setup later; completed archives are reused.")
}

function DownloadMegaSwitchAssets {
    EnsureDir $MegaAssetCache
    $RemoteArchives = @(GetMegaDesiredRemoteArchives)
    foreach ($RemotePath in $RemoteArchives) {
        DownloadMegaArchiveWithWatchdog $RemotePath
    }
    Stamp "Selective MEGA model/animation download finished."
}

function FindSwitchAssetArchives {
    $Roots = @(
        $RepoRoot,
        (Join-Path $RepoRoot "switch-assets"),
        (Join-Path $env:USERPROFILE "Downloads"),
        (Join-Path $env:USERPROFILE "Desktop"),
        $MegaAssetCache
    ) | Select-Object -Unique

    $Found = New-Object System.Collections.Generic.List[string]
    foreach ($Root in $Roots) {
        if (-not $Root -or -not (Test-Path $Root)) { continue }
        $Files = Get-ChildItem $Root -File -Recurse -ErrorAction SilentlyContinue | Where-Object {
            ($_.Extension -in @(".zip", ".7z")) -and
            ($_.BaseName -match "(?i)(Poke|Pokemon)")
        }
        foreach ($File in $Files) {
            if (-not $Found.Contains($File.FullName)) { $Found.Add($File.FullName) }
        }
    }
    return $Found.ToArray()
}

function ImportSwitchGameAssets([string]$PythonCommand, [string]$Blender) {
    Step "STEP 6/7 - Importing Switch-game Pokemon models"
    if ($SkipSwitchAssets) {
        Stamp "Skipping Switch-game asset import because -SkipSwitchAssets was supplied."
        return
    }
    if (-not $Blender) {
        throw "Blender is unavailable, so Switch-game models cannot be converted."
    }
    $AllArchives = @(FindSwitchAssetArchives)
    $ModelArchives = @($AllArchives | Where-Object { (Split-Path $_ -Leaf) -notmatch "(?i)(anim|animation|pokeanim)" })
    if ($ModelArchives.Count -eq 0) {
        Stamp "No local Switch-game model archives were found."
        DownloadMegaSwitchAssets
        $AllArchives = @(FindSwitchAssetArchives)
        $ModelArchives = @($AllArchives | Where-Object { (Split-Path $_ -Leaf) -notmatch "(?i)(anim|animation|pokeanim)" })
    }
    if ($ModelArchives.Count -eq 0) {
        throw "The selective MEGA download completed, but no Pokemon model archives were discovered."
    }
    $AnimArchives = @($AllArchives | Where-Object { (Split-Path $_ -Leaf) -match "(?i)(anim|animation|pokeanim)" })
    Stamp ("Found " + $ModelArchives.Count + " Switch model archive(s) and " + $AnimArchives.Count + " animation archive(s).")
    foreach ($Archive in $ModelArchives) { Stamp ("  model: " + (Split-Path -Leaf $Archive)) }
    foreach ($Archive in $AnimArchives) { Stamp ("  anim:  " + (Split-Path -Leaf $Archive)) }
    $Archives = $AllArchives
    if ($Archives | Where-Object { $_.ToLowerInvariant().EndsWith(".7z") }) {
        [void](EnsureSevenZip)
    }
    $Script = Join-Path $RepoRoot "scripts\import_switch_game_assets.py"
    if (-not (Test-Path $Script)) { throw "Switch model importer script is missing." }
    $Args = @("-u", $Script)
    $Args += $Archives
    $Args += @("--blender", $Blender)
    $env:PYTHONUNBUFFERED = "1"
    Push-Location $RepoRoot
    try {
        if ($PythonCommand -eq "py") { & py -3 @Args } else { & python @Args }
        $ImportExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($ImportExit -ne 0) { throw "Switch-game model import failed with exit code $ImportExit." }
    Stamp "Switch-game model import finished."
}

function InstallModels([string]$PythonCommand) {
    Step "STEP 5/7 - Preparing offline 3D model pack"
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
    $GenericCatalog = Join-Path $Pack "generic_model_catalog.tsv"

    if ((-not $RefreshModels) -and (Test-Path $Info) -and (Test-Path $GenericCatalog)) {
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
    } elseif ((-not $RefreshModels) -and (Test-Path $Info)) {
        Stamp "Existing model pack predates the fallback catalog; rebuilding its catalog once."
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
    Step "STEP 7/7 - Building Windows EXE"
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
    Stamp "One-click mode: tools, Switch model import, offline model pack, and Windows build are automatic."
    Stamp "Nothing is frozen if timestamps keep appearing or a download/build counter changes."
    Stamp ("Log file: " + $LogFile)

    BootstrapJdk
    $Gradle = BootstrapGradle
    $Python = EnsurePython
    $Blender = EnsureBlender
    # Build the generic fallback pack first, then let validated Switch models
    # override it. This keeps names/fallbacks deterministic and prevents a later
    # generic catalog refresh from hiding the Switch import.
    $Pack = InstallModels $Python
    ImportSwitchGameAssets $Python $Blender
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