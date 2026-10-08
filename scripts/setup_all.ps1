param(
    [switch]$SkipSwitchAssets,
    [switch]$SkipInstall,
    [switch]$SwitchAssetsOnly
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $RepoRoot ".tools"
$DistDir = Join-Path $RepoRoot "dist"
$LogFile = Join-Path $RepoRoot "setup-all.log"
$script:TranscriptStarted = $false
$GradleVersion = "9.6.0"
$JdkMajor = "22"
$BlenderPortableVersion = "4.5.14"
$BlenderPortableUrl = "https://mirror.blender.org/release/Blender4.5/blender-4.5.14-windows-x64.zip"
$MegaFolderLink = "https://mega.nz/folder/elJhVC5D#NU-yzmXuTlsIIzXAMLKVaA"
$MegaAssetCache = Join-Path $RepoRoot ".cache\mega-switch-assets"
$MegaNoProgressTimeoutSeconds = 300
$MegaDownloadRetries = 3

function GetTargetPackageVersion {
    $BuildFile = Join-Path $RepoRoot "desktopApp\build.gradle.kts"
    if (-not (Test-Path $BuildFile)) { return $null }
    $Content = Get-Content $BuildFile -Raw
    $Match = [regex]::Match($Content, 'packageVersion\s*=\s*"([^"]+)"')
    if ($Match.Success) { return $Match.Groups[1].Value }
    return $null
}

$script:TargetPackageVersion = GetTargetPackageVersion

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
    Step "STEP 1/6 - Checking JDK 22"
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
    Step "STEP 2/6 - Checking Gradle"
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
    Step "STEP 3/6 - Checking Python"
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
    Step "STEP 4/6 - Checking Blender"

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
        $IsArchive = $Leaf.EndsWith(".zip", [StringComparison]::OrdinalIgnoreCase) -or
            $Leaf.EndsWith(".7z", [StringComparison]::OrdinalIgnoreCase)
        $IsSwitchPokemonPack = $Leaf -match "(?i)^(ZA|SV|LA|PLA|SwSh|LGPE|BDSP)[-_ ]*Poke"
        $HasGameToken = $Leaf -match "(?i)(^|[-_ .])(ZA|SV|LA|PLA|SwSh|LGPE|BDSP)([-_ .]|$)"
        $HasTextureToken = $Leaf -match "(?i)(PokeTex|Texture|Textures|TexPack|Tex)"
        $IsSwitchTexturePack = $HasGameToken -and $HasTextureToken
        if ($IsArchive -and ($IsSwitchPokemonPack -or $IsSwitchTexturePack)) {
            if (-not $Selected.Contains($Path)) { $Selected.Add($Path) }
        }
    }

    if ($Selected.Count -eq 0) {
        throw "MEGA metadata scan succeeded, but no Pokemon model/animation archives matched."
    }

    Stamp ("Selected " + $Selected.Count + " Pokemon model/animation/texture archive(s) instead of the whole folder.")
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
    Stamp "Selective MEGA model/animation/texture download finished."
}

function FindSwitchAssetArchives {
    $Plans = @(
        @{ Root = $RepoRoot; Recurse = $false },
        @{ Root = (Join-Path $RepoRoot "switch-assets"); Recurse = $true },
        @{ Root = (Join-Path $env:USERPROFILE "Downloads"); Recurse = $true },
        @{ Root = (Join-Path $env:USERPROFILE "Desktop"); Recurse = $true },
        @{ Root = $MegaAssetCache; Recurse = $true }
    )

    $Found = New-Object System.Collections.Generic.List[string]
    foreach ($Plan in $Plans) {
        $Root = $Plan.Root
        if (-not $Root -or -not (Test-Path $Root)) { continue }

        $Args = @{
            Path = $Root
            File = $true
            ErrorAction = "SilentlyContinue"
        }
        if ($Plan.Recurse) { $Args["Recurse"] = $true }

        $Files = Get-ChildItem @Args | Where-Object {
            if ($_.Extension -notin @(".zip", ".7z")) { return $false }

            $Name = $_.BaseName
            $PokemonPack = $Name -match "(?i)^(ZA|SV|LA|PLA|SwSh|LGPE|BDSP)[-_ ]*Poke"
            $HasGameToken = $Name -match "(?i)(^|[-_ .])(ZA|SV|LA|PLA|SwSh|LGPE|BDSP)([-_ .]|$)"
            $HasTextureToken = $Name -match "(?i)(PokeTex|Texture|Textures|TexPack|Tex)"
            return $PokemonPack -or ($HasGameToken -and $HasTextureToken)
        }
        foreach ($File in $Files) {
            if (-not $Found.Contains($File.FullName)) { $Found.Add($File.FullName) }
        }
    }
    return $Found.ToArray()
}

function ImportSwitchGameAssets([string]$PythonCommand, [string]$Blender) {
    Step "STEP 5/6 - Importing Switch-game Pokemon models"
    if ($SkipSwitchAssets) {
        Stamp "Skipping Switch-game asset import because -SkipSwitchAssets was supplied."
        return
    }
    if (-not $Blender) {
        throw "Blender is unavailable, so Switch-game models cannot be converted."
    }
    $AllArchives = @(FindSwitchAssetArchives)
    $ModelArchives = @($AllArchives | Where-Object {
        (Split-Path $_ -Leaf) -notmatch "(?i)(anim|animation|pokeanim|poketex|texture)"
    })

    # Restore the source archives already downloaded for these models.
    # Only download original archives if none are present locally.
    try {
        if ($ModelArchives.Count -eq 0) { DownloadMegaSwitchAssets }
        $AllArchives = @(FindSwitchAssetArchives)
        $ModelArchives = @($AllArchives | Where-Object {
            (Split-Path $_ -Leaf) -notmatch "(?i)(anim|animation|pokeanim|poketex|texture)"
        })
    } catch {
        if ($ModelArchives.Count -eq 0) { throw }
        Stamp ("MEGA sync unavailable; continuing with validated local archives: " + $_.Exception.Message)
    }
    if ($ModelArchives.Count -eq 0) {
        throw "The selective MEGA download completed, but no Pokemon model archives were discovered."
    }
    $AnimArchives = @($AllArchives | Where-Object {
        (Split-Path $_ -Leaf) -match "(?i)(anim|animation|pokeanim)" -and
        (Split-Path $_ -Leaf) -notmatch "(?i)(poketex|texture)"
    })
    $TextureArchives = @($AllArchives | Where-Object {
        (Split-Path $_ -Leaf) -match "(?i)(poketex|texture)"
    })
    Stamp ("Found " + $ModelArchives.Count + " Switch model archive(s), " + $AnimArchives.Count + " animation archive(s), and " + $TextureArchives.Count + " texture archive(s).")
    foreach ($Archive in $ModelArchives) { Stamp ("  model: " + (Split-Path -Leaf $Archive)) }
    foreach ($Archive in $AnimArchives) { Stamp ("  anim:  " + (Split-Path -Leaf $Archive)) }
    foreach ($Archive in $TextureArchives) { Stamp ("  tex:   " + (Split-Path -Leaf $Archive)) }
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
    if ($ImportExit -ne 0) {
        Stamp "Some original models could not be converted (exit $ImportExit). Restoring the usable exports that remain."
        # The caller requires a nonempty restored catalog before building.
        return
    }
    Stamp "Switch-game model import finished."
}

function RestoreInstalledSwitchExports([string]$PythonCommand) {
    Stamp "Restoring animated Switch GLBs with valid embedded textures."
    $Restore = Join-Path $RepoRoot "scripts\restore_switch_models.py"
    if ($PythonCommand -eq "py") { & py -3 -u $Restore | ForEach-Object { Write-Host $_ } }
    else { & python -u $Restore | ForEach-Object { Write-Host $_ } }
    $RestoreExit = $LASTEXITCODE
    if ($RestoreExit -eq 0) { return $true }
    if ($RestoreExit -eq 2) { return $false }
    throw "Switch export restoration failed with exit code $RestoreExit."
}

function RestoreOrImportSwitchExports([string]$PythonCommand) {
    $Recovered = RestoreInstalledSwitchExports $PythonCommand
    $OriginalArchives = @(FindSwitchAssetArchives | Where-Object {
        (Split-Path $_ -Leaf) -notmatch "(?i)(anim|animation|pokeanim|poketex|texture)"
    })
    # Only textured animated GLBs are reused; missing or textureless models reconvert.
    if ((-not $Recovered) -or ($OriginalArchives.Count -gt 0 -and (-not $SkipSwitchAssets))) {
        if ($SkipSwitchAssets) { throw "No original Switch exports remain. Run setup-all.bat full to restore the downloaded source archives." }
        $Blender = EnsureBlender
        ImportSwitchGameAssets $PythonCommand $Blender
        $Recovered = RestoreInstalledSwitchExports $PythonCommand
    }
    if (-not $Recovered) {
        throw "No original animated Switch models could be restored. No older model pack was activated. Run setup-all.bat full with the original downloaded archives."
    }
}

function PreflightSwitchImporter([string]$PythonCommand) {
    Step "PRECHECK - Validating Switch importer"

    $Importer = Join-Path $RepoRoot "scripts\import_switch_game_assets.py"
    $BlenderHelper = Join-Path $RepoRoot "scripts\blender_import_switch_game_model.py"
    if (-not (Test-Path $Importer) -or -not (Test-Path $BlenderHelper)) {
        throw "Importer preflight files are missing."
    }

    Stamp "Compiling Python importer scripts..."
    if ($PythonCommand -eq "py") {
        & py -3 -m py_compile $Importer $BlenderHelper
    } else {
        & python -m py_compile $Importer $BlenderHelper
    }
    if ($LASTEXITCODE -ne 0) { throw "Python importer syntax preflight failed." }

    Stamp "Running Switch importer matching/cache self-tests..."
    if ($PythonCommand -eq "py") {
        & py -3 -u $Importer --self-test
    } else {
        & python -u $Importer --self-test
    }
    if ($LASTEXITCODE -ne 0) { throw "Switch importer self-tests failed." }

    Stamp "Switch importer preflight passed."
}

function PreflightCode([string]$PythonCommand, [string]$GradleBat) {
    Step "PRECHECK - Validating importer and desktop renderer"
    PreflightSwitchImporter $PythonCommand

    Stamp "Validating browser code and compiling native desktop viewer before expensive asset work..."
    if (Get-Command node.exe -ErrorAction SilentlyContinue) {
        & node.exe (Join-Path $RepoRoot "scripts\check_shared_app.js")
        if ($LASTEXITCODE -ne 0) { throw "Shared app validation failed." }
    }
    Push-Location $RepoRoot
    try {
        & $GradleBat --console=plain --no-daemon :desktopApp:verifyDesktop
        if ($LASTEXITCODE -ne 0) { throw "Desktop Kotlin preflight compile failed." }
    } finally {
        Pop-Location
    }

    Stamp "Code preflight passed."
}

function BuildWindows([string]$GradleBat) {
    Step "STEP 6/6 - Building Windows installers"
    Push-Location $RepoRoot
    try {
        Stamp "Starting Gradle desktop build. Gradle output will remain visible."
        & $GradleBat --console=plain --no-daemon :desktopApp:packageMsi :desktopApp:packageExe
        if ($LASTEXITCODE -ne 0) { throw "Windows installer build failed." }
    } finally {
        Pop-Location
    }
    Stamp "Gradle build completed."
}

function CollectInstallers {
    Step "Collecting final Windows installers"
    EnsureDir $DistDir

    $MsiSource = Get-ChildItem (Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\msi") -Filter *.msi -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    $ExeSource = Get-ChildItem (Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\exe") -Filter *.exe -File -Recurse -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $MsiSource -and -not $ExeSource) {
        throw "No Windows installer output was found after a successful Gradle build."
    }

    $Result = @{}
    if ($MsiSource) {
        $Msi = Join-Path $DistDir "Pokedex-3D-Max-Windows.msi"
        Copy-Item $MsiSource.FullName $Msi -Force
        Stamp ("Final MSI: " + $Msi)
        Stamp ("MSI size: " + [math]::Round((Get-Item $Msi).Length / 1MB, 1).ToString() + " MB")
        $Result["Msi"] = $Msi
    }
    if ($ExeSource) {
        $Exe = Join-Path $DistDir "Pokedex-3D-Max-Windows.exe"
        Copy-Item $ExeSource.FullName $Exe -Force
        Stamp ("Final EXE: " + $Exe)
        Stamp ("EXE size: " + [math]::Round((Get-Item $Exe).Length / 1MB, 1).ToString() + " MB")
        $Result["Exe"] = $Exe
    }

    $Image = Join-Path $RepoRoot "desktopApp\build\compose\binaries\main\app\Pokedex 3D Max"
    if (Test-Path $Image) {
        $Portable = Join-Path $DistDir "Pokedex-3D-Max-Portable"
        EnsureDir $Portable
        Copy-Item (Join-Path $Image "*") $Portable -Recurse -Force
        $Result["Portable"] = Join-Path $Portable "Pokedex 3D Max.exe"
        Stamp ("Portable app (no installer required): " + $Result["Portable"])
    }
    return $Result
}

function FindInstalledPokedex {
    $Roots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($Root in $Roots) {
        $Match = Get-ItemProperty $Root -ErrorAction SilentlyContinue |
            Where-Object {
                $_.DisplayName -and
                ($_.DisplayName -eq "Pokedex 3D Max" -or $_.DisplayName -eq "Pokedex3DMax")
            } |
            Select-Object -First 1
        if ($Match) { return $Match }
    }
    return $null
}

function InstallOrUpdateWindows([hashtable]$Installers) {
    if ($SkipInstall) {
        Stamp "Skipping installer launch because -SkipInstall was supplied."
        return
    }

    $Installed = FindInstalledPokedex
    if ($Installed) {
        $Version = if ($Installed.DisplayVersion) { $Installed.DisplayVersion } else { "unknown" }
        Stamp ("Existing Pokedex 3D Max installation detected (version " + $Version + ").")
        Stamp "Updating the existing installation automatically."
    } else {
        Stamp "No existing Pokedex 3D Max installation detected."
        Stamp "Installing Pokedex 3D Max automatically."
    }

    if ($Installers.ContainsKey("Msi") -and (Test-Path $Installers["Msi"])) {
        $Msi = $Installers["Msi"]
        $InstallerLog = Join-Path $DistDir "windows-install.log"
        $Arguments = @(
            "/i",
            ('"' + $Msi + '"'),
            "/passive",
            "/norestart",
            "/L*v",
            ('"' + $InstallerLog + '"')
        )
        if ($Installed -and $script:TargetPackageVersion -and $Installed.DisplayVersion -eq $script:TargetPackageVersion) {
            Stamp "Same package version detected; running an in-place repair/update."
            $Arguments += @("REINSTALL=ALL", "REINSTALLMODE=amus")
        }
        Stamp ("Launching Windows Installer: " + $Msi)
        $Process = Start-Process -FilePath "msiexec.exe" -ArgumentList $Arguments -Wait -PassThru
        if ($Process.ExitCode -eq 1602) {
            Stamp "Windows cancelled installation (1602). The new build is ready, but the installed app was not updated."
            Stamp ("Installer details: " + $InstallerLog)
            if ($Installers.ContainsKey("Portable")) {
                Stamp ("Run the updated app without installing: " + $Installers["Portable"])
                return
            }
            throw "Installation was cancelled. Rerun the MSI in dist to finish installing. Log: $InstallerLog"
        }
        if ($Process.ExitCode -notin @(0, 1641, 3010)) {
            throw "Pokedex 3D Max MSI install/update failed with exit code $($Process.ExitCode). Details: $InstallerLog"
        }
        if ($Process.ExitCode -eq 3010) {
            Stamp "Install/update succeeded; Windows reports that a restart may be required."
        } else {
            Stamp "Install/update completed successfully."
        }
        return
    }

    if ($Installers.ContainsKey("Exe") -and (Test-Path $Installers["Exe"])) {
        $Exe = $Installers["Exe"]
        Stamp "MSI was unavailable; launching the EXE installer fallback."
        $Process = Start-Process -FilePath $Exe -Wait -PassThru
        if ($Process.ExitCode -ne 0) {
            throw "Pokedex 3D Max EXE installer exited with code $($Process.ExitCode)."
        }
        return
    }

    throw "No usable Windows installer was collected."
}

EnsureDir $ToolsDir
EnsureDir $DistDir

function StartSetupTranscript {
    $Candidates = New-Object System.Collections.Generic.List[string]
    [void]$Candidates.Add($LogFile)

    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $FallbackLog = Join-Path $RepoRoot ("setup-all-" + $Timestamp + ".log")
    [void]$Candidates.Add($FallbackLog)

    foreach ($Candidate in $Candidates) {
        try {
            Start-Transcript -Path $Candidate -Force -ErrorAction Stop | Out-Null
            $script:TranscriptStarted = $true
            $script:LogFile = $Candidate
            return
        } catch {
            Write-Host ("Logging warning: could not start transcript at " + $Candidate)
            Write-Host ("  " + $_.Exception.Message)
        }
    }

    $script:TranscriptStarted = $false
    Write-Host "Logging warning: PowerShell transcription is unavailable."
    Write-Host "Setup will continue without transcript logging."
}

StartSetupTranscript

try {
    Write-Host "============================================================"
    Write-Host "        Pokedex 3D Max - Windows Setup"
    Write-Host "============================================================"
    Stamp "One-click mode: tools, strict Switch model import, and Windows build are automatic."
    Stamp "Nothing is frozen if timestamps keep appearing or a download/build counter changes."
    Stamp ("Log file: " + $LogFile)

    if ($SwitchAssetsOnly) {
        Stamp "Switch-assets-only mode: skipping JDK, Gradle, fallback-pack, and Windows packaging."
        $Python = EnsurePython
        PreflightSwitchImporter $Python
        RestoreOrImportSwitchExports $Python
        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Stamp "SUCCESS - regular animated Switch exports restored with valid textures."
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host ("Offline models: " + (Join-Path $env:LOCALAPPDATA "Pokedex3DMax\offline-models"))
        return
    }

    BootstrapJdk
    $Gradle = BootstrapGradle
    $Python = EnsurePython
    PreflightCode $Python $Gradle
    # Restore the user's original Switch models. Do not replace them with the
    # online pack or download the old generic models during restoration.
    RestoreOrImportSwitchExports $Python
    $Pack = Join-Path $env:LOCALAPPDATA "Pokedex3DMax\offline-models"
    BuildWindows $Gradle
    $Installers = CollectInstallers

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Stamp "SUCCESS - Windows build is ready."
    Write-Host "============================================================" -ForegroundColor Green
    if ($Installers.ContainsKey("Msi")) { Write-Host ("MSI: " + $Installers["Msi"]) }
    if ($Installers.ContainsKey("Exe")) { Write-Host ("EXE: " + $Installers["Exe"]) }
    if ($Pack) { Write-Host ("Offline models: " + $Pack) }
    InstallOrUpdateWindows $Installers
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
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
