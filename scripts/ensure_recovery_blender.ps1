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
        foreach ($url in $urls) {
            Write-Host "Downloading Blender $version (resuming any partial download): $url"
            # -C - resumes the existing ZIP instead of restarting when the server supports ranges.
            # --retry-all-errors also retries abrupt EOF/disconnect failures.
            & $curl.Source --location --fail --retry 8 --retry-delay 5 --retry-all-errors --connect-timeout 30 --continue-at - --output $zip $url
            $result = $LASTEXITCODE
            if ($result -ne 0) {
                Write-Warning "Blender download ended with curl code $result; trying another source."
                continue
            }
            try {
                $archive = [IO.Compression.ZipFile]::OpenRead($zip)
                try {
                    $validZip = (($archive.Entries | Where-Object { $_.FullName -match '(^|/)blender\.exe$' } | Select-Object -First 1) -ne $null)
                } finally { $archive.Dispose() }
            } catch {
                Write-Warning "Downloaded archive is incomplete: $($_.Exception.Message)"
                $validZip = $false
            }
            if ($validZip) { break }
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
