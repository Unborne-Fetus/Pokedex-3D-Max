param(
    [string]$Repository = $(if ($env:POKEDEX3D_MODEL_PACK_REPO) { $env:POKEDEX3D_MODEL_PACK_REPO } else { "Unborne-Fetus/Pokedex-3D-Max" }),
    [string]$Tag = $(if ($env:POKEDEX3D_MODEL_PACK_TAG) { $env:POKEDEX3D_MODEL_PACK_TAG } else { "model-pack-v7" })
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Output = Join-Path $RepoRoot ("dist\" + $Tag)
$Builder = Join-Path $RepoRoot "scripts\remote_model_pack.py"
$BaseUrl = "https://github.com/" + $Repository + "/releases/download/" + $Tag

if (-not (Test-Path $Builder)) {
    throw "scripts\remote_model_pack.py is missing."
}
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required to publish the model pack."
}

Write-Host "============================================================"
Write-Host "      Pokedex 3D Max - Publish Switch Model Pack"
Write-Host "============================================================"
Write-Host ("Repository: " + $Repository)
Write-Host ("Release tag: " + $Tag)
Write-Host ""
Write-Host "This publishes converted GLBs, not the original downloaded archives."
Write-Host "Only publish these assets where you have permission to distribute them."
Write-Host ""

& gh auth status
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI is not authenticated. Run gh auth login first."
}

$Python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
} else {
    throw "Python was not found."
}

if (Test-Path $Output) {
    Remove-Item -Recurse -Force $Output
}
New-Item -ItemType Directory -Force -Path $Output | Out-Null

Write-Host "Building validated model-pack shards..."
if ($Python -eq "py") {
    & py -3 -u $Builder build --output $Output --base-url $BaseUrl --shard-size 100
} else {
    & python -u $Builder build --output $Output --base-url $BaseUrl --shard-size 100
}
if ($LASTEXITCODE -ne 0) {
    throw "Model-pack build failed."
}

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    & gh release view $Tag --repo $Repository *> $null
    $ReleaseExists = ($LASTEXITCODE -eq 0)
} finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}

if (-not $ReleaseExists) {
    Write-Host ("Creating release " + $Tag + "...")
    & gh release create $Tag --repo $Repository --title ("Pokedex 3D Max Switch Model Pack " + $Tag) --notes "Validated preconverted Switch-model pack for Pokedex 3D Max. Setup verifies SHA-256 checksums and falls back to locally downloaded source archives if this release is unavailable."
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create GitHub release."
    }
}

$Files = @(Get-ChildItem $Output -File | Sort-Object Name)
if ($Files.Count -eq 0) {
    throw "Model-pack build produced no release files."
}

Write-Host ("Uploading " + $Files.Count + " release asset(s)...")
$Paths = @($Files | ForEach-Object { $_.FullName })
& gh release upload $Tag @Paths --repo $Repository --clobber
if ($LASTEXITCODE -ne 0) {
    throw "GitHub release upload failed."
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Model pack published successfully." -ForegroundColor Green
Write-Host ("Manifest: " + $BaseUrl + "/model-pack-manifest.json")
Write-Host "Downloaded original Switch archives were not modified."
Write-Host "============================================================" -ForegroundColor Green
