param()
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot '.tools'
$reportDir = Join-Path $repoRoot '.cache\remaining-model-diagnosis'
New-Item -ItemType Directory -Path $toolsDir, $reportDir -Force | Out-Null
Add-Type -AssemblyName System.IO.Compression

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
        "https://download.blender.org/release/Blender4.5/blender-$version-windows-x64.zip",
        "https://mirror.blender.org/release/Blender4.5/blender-$version-windows-x64.zip"
    )
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { throw 'curl.exe is required for resumable Blender downloads (included with Windows 10/11).' }

    $validZip = $false
    if (Test-Path -LiteralPath $zip) {
        try {
            Add-Type -AssemblyName System.IO.Compression
            $archive = [IO.Compression.ZipFile]::OpenRead($zip)
            try {
                $validZip = (($archive.Entries | Where-Object { $_.FullName -match '(^|/)blender\.exe$' } | Select-Object -First 1) -ne $null)
            } finally { $archive.Dispose() }
        } catch { $validZip = $false }
    }

    if (-not $validZip) {
        # A partial ZIP can belong to a different server response or version.
        # Never append to it after a 403 / failed resume; try a clean temporary
        # download without risking the user's existing partial archive.
        foreach ($url in $urls) {
            $fresh = "$zip.fresh"
            Write-Host "Downloading Blender $version from $url"
            if (Test-Path -LiteralPath $fresh) { Remove-Item -LiteralPath $fresh -Force }
            $resumed = $false
            if ((Test-Path -LiteralPath $zip) -and ((Get-Item -LiteralPath $zip).Length -gt 0)) {
                Write-Host "Attempting to resume the existing download..."
                & $curl.Source --location --fail --retry 2 --retry-delay 2 --connect-timeout 30 --continue-at - --output $zip $url
                $resumed = ($LASTEXITCODE -eq 0)
            }
            if ($resumed) {
                try {
                    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
                    try {
                        $validZip = ((Get-Item -LiteralPath $zip).Length -gt 350MB -and
                            (($archive.Entries | Where-Object { $_.FullName -match '(^|/)blender\\.exe$' } | Select-Object -First 1) -ne $null))
                    } finally { $archive.Dispose() }
                } catch { $validZip = $false }
                if ($validZip) { break }
                Write-Warning "Resumed Blender ZIP failed validation; trying clean download."
            }
            Write-Host "Downloading a clean ZIP (no range request)..."
            & $curl.Source --location --fail --retry 2 --retry-delay 2 --connect-timeout 30 --output $fresh $url
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Clean download failed at $url; trying the next source."
                if (Test-Path -LiteralPath $fresh) { Remove-Item -LiteralPath $fresh -Force }
                continue
            }
            try {
                $archive = [IO.Compression.ZipFile]::OpenRead($fresh)
                try {
                    $validZip = ((Get-Item -LiteralPath $fresh).Length -gt 350MB -and
                        (($archive.Entries | Where-Object { $_.FullName -match '(^|/)blender\\.exe$' } | Select-Object -First 1) -ne $null))
                } finally { $archive.Dispose() }
            } catch {
                Write-Warning "Clean Blender ZIP failed validation: $($_.Exception.Message)"
                $validZip = $false
            }
            if ($validZip) {
                Move-Item -LiteralPath $fresh -Destination $zip -Force
                break
            }
            if (Test-Path -LiteralPath $fresh) { Remove-Item -LiteralPath $fresh -Force }
        }
    }
    if (-not $validZip) {
        throw "Blender download incomplete after retries. Partial archive is preserved at $zip so the next run can resume."
    }
    Write-Host 'Blender archive verified. Extracting...'
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $installDir -Force
    $blender = Find-Blender
}
if (-not $blender) { throw 'Blender executable still missing after extraction.' }
$target = Join-Path $reportDir 'blender-path.txt'
[IO.File]::WriteAllText($target, $blender + [Environment]::NewLine)
Write-Host "Using Blender: $blender"
