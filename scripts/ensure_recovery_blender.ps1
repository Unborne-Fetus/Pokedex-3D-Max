param()
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot '.tools'
$reportDir = Join-Path $repoRoot '.cache\remaining-model-diagnosis'
New-Item -ItemType Directory -Path $toolsDir, $reportDir -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression
Write-Host '[Blender setup v4] Checking existing portable installation and cached ZIP files.'

function Find-Blender {
    $cmd = Get-Command blender -ErrorAction SilentlyContinue
    if ($cmd -and (Test-Path -LiteralPath $cmd.Source -PathType Leaf)) { return $cmd.Source }
    foreach ($root in @($toolsDir, (Join-Path $env:ProgramFiles 'Blender Foundation'))) {
        if ($root -and (Test-Path -LiteralPath $root)) {
            $found = Get-ChildItem -LiteralPath $root -Filter blender.exe -File -Recurse -ErrorAction SilentlyContinue |
                Select-Object -First 1 -ExpandProperty FullName
            if ($found) { return $found }
        }
    }
    return $null
}

$blender = Find-Blender
if (-not $blender) {
    $version = '4.5.14'
    $zip = Join-Path $toolsDir "blender-$version.zip"
    $installDir = Join-Path $toolsDir "blender-$version"
    $urls = @(
        "https://mirror.blender.org/release/Blender4.5/blender-$version-windows-x64.zip",
        "https://download.blender.org/release/Blender4.5/blender-$version-windows-x64.zip"
    )
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw 'curl.exe is required for resumable Blender downloads (included with Windows 10/11).' }

    function Test-BlenderZip([string]$ArchivePath) {
        if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) { return $false }
        try {
            $size = (Get-Item -LiteralPath $ArchivePath).Length
            $archive = [IO.Compression.ZipFile]::OpenRead($ArchivePath)
            try {
                $exe = $archive.Entries | Where-Object {
                    $_.FullName.Replace('\\', '/').EndsWith('/blender.exe', [StringComparison]::OrdinalIgnoreCase) -or
                    $_.FullName.Equals('blender.exe', [StringComparison]::OrdinalIgnoreCase)
                } | Select-Object -First 1
                if ($exe -and $size -gt 100MB) {
                    Write-Host "Verified Blender ZIP: $ArchivePath ($size bytes)"
                    return $true
                }
                Write-Warning "ZIP is readable but Blender executable was not found (size $size bytes; entries $($archive.Entries.Count))."
            } finally { $archive.Dispose() }
        } catch {
            Write-Warning "ZIP could not be opened: $ArchivePath : $($_.Exception.Message)"
        }
        return $false
    }

    $fresh = "$zip.fresh"
    $validZip = Test-BlenderZip $zip
    if (-not $validZip -and (Test-BlenderZip $fresh)) {
        Move-Item -LiteralPath $fresh -Destination $zip -Force
        $validZip = $true
    }
    if (-not $validZip) {
        # Invalid old partial downloads must never be resumed: range servers can
        # answer 403 or append the wrong representation to the old bytes.
        foreach ($url in $urls) {
            Write-Host "Downloading a clean Blender archive from $url"
            if (Test-Path -LiteralPath $fresh) { Remove-Item -LiteralPath $fresh -Force }
            # Windows PowerShell 5.1 promotes curl's stderr progress/errors to
            # PowerShell errors when ErrorActionPreference is Stop. Restore it
            # immediately after the native command and check the actual exit code.
            $previousErrorAction = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                & $curl.Source --location --fail --retry 2 --retry-delay 2 --connect-timeout 30 --progress-bar --output $fresh $url
                $curlExitCode = $LASTEXITCODE
            } finally {
                $ErrorActionPreference = $previousErrorAction
            }
            if ($curlExitCode -ne 0) {
                Write-Warning "Download failed with curl exit code $curlExitCode."
                continue
            }
            if (Test-BlenderZip $fresh) {
                Move-Item -LiteralPath $fresh -Destination $zip -Force
                $validZip = $true
                break
            }
            Write-Warning "The downloaded file was not a valid Blender archive; trying another source."
        }
    }
    if (-not $validZip) {
        throw "No valid Blender ZIP found. Check the ZIP verification warnings above. Saved files: $zip and $fresh"
    }
    Write-Host 'Blender archive verified. Extracting...'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    try {
        Expand-Archive -LiteralPath $zip -DestinationPath $installDir -Force -ErrorAction Stop
    } catch {
        throw "Blender ZIP verified, but extraction failed: $($_.Exception.Message). Archive retained at $zip"
    }
    $blender = Find-Blender
}
if (-not $blender) { throw 'Blender executable still missing after extraction.' }
$target = Join-Path $reportDir 'blender-path.txt'
[IO.File]::WriteAllText($target, $blender + [Environment]::NewLine)
Write-Host "Using Blender: $blender"
