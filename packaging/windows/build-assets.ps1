[CmdletBinding()]
param(
    [string]$PythonExe = "py.exe",
    [string]$ReleaseVersion = "2.3.0",
    [string]$OutputRoot = "$PSScriptRoot\dist",
    [string]$ArgosModelPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PackageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$StageRoot = Join-Path $OutputRoot "stage-standard"
$BundleRoot = Join-Path $OutputRoot "bundle-standard"
$ManifestTemplate = Join-Path $PSScriptRoot "manifest.standard.json"
$ManifestOutput = Join-Path $BundleRoot "manifest.standard.release.json"

foreach ($Path in @($StageRoot, $BundleRoot)) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

$Wheelhouse = Join-Path $StageRoot "wheelhouse"
New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null
& $PythonExe -3.13 -m pip download --dest $Wheelhouse "${PackageRoot}[browser,pdf,translation]"
if ($LASTEXITCODE -ne 0) { throw "pip download failed" }
& $PythonExe -3.13 -m pip wheel --no-deps --wheel-dir $Wheelhouse $PackageRoot
if ($LASTEXITCODE -ne 0) { throw "project wheel build failed" }

$BrowserRoot = Join-Path $StageRoot "ms-playwright"
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot
& $PythonExe -3.13 -m pip install playwright argostranslate
if ($LASTEXITCODE -ne 0) { throw "builder dependencies failed" }
& $PythonExe -3.13 -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Playwright Chromium download failed" }

if (-not $ArgosModelPath) {
    $ArgosModelPath = (& $PythonExe -3.13 -c "import argostranslate.package as p; p.update_package_index(); x=next(x for x in p.get_available_packages() if x.from_code=='en' and x.to_code=='zh'); print(x.download())" | Select-Object -Last 1)
}
if (-not (Test-Path $ArgosModelPath -PathType Leaf)) { throw "Argos model download failed" }

$PythonInstaller = Join-Path $StageRoot "python-3.13.15-amd64.exe"
Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe" -OutFile $PythonInstaller

$AssetPaths = @{
    "python-runtime" = $PythonInstaller
    "python-wheelhouse" = Join-Path $StageRoot "wheelhouse.zip"
    "playwright-chromium" = Join-Path $StageRoot "playwright-chromium.zip"
    "argos-en-zh-model" = $ArgosModelPath
}
Compress-Archive -Path (Join-Path $Wheelhouse "*") -DestinationPath $AssetPaths["python-wheelhouse"] -Force
Compress-Archive -Path (Join-Path $BrowserRoot "*") -DestinationPath $AssetPaths["playwright-chromium"] -Force

$Manifest = Get-Content -LiteralPath $ManifestTemplate -Raw -Encoding UTF8 | ConvertFrom-Json
$Manifest.manifest_version = "$ReleaseVersion-release"
$Manifest.release_ready = $true
foreach ($Asset in $Manifest.assets) {
    $SourcePath = $AssetPaths[[string]$Asset.id]
    if (-not $SourcePath -or -not (Test-Path $SourcePath -PathType Leaf)) {
        throw "Missing built asset: $($Asset.id)"
    }
    $Destination = Join-Path $BundleRoot ([string]$Asset.relative_path)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $SourcePath -Destination $Destination -Force
    $Asset.size = (Get-Item -LiteralPath $Destination).Length
    $Asset.sha256 = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
}

$LicenseFile = Join-Path $BundleRoot "THIRD_PARTY_LICENSES.txt"
@"
Nuoyan Windows standard asset bundle $ReleaseVersion

Python runtime: Python Software Foundation License
Python wheelhouse: inspect each wheel's METADATA and license files before release approval
Playwright: Apache-2.0; Chromium notices are included in the browser distribution
Argos Translate: MIT; the selected en-to-zh model source and license require release review
"@ | Set-Content -LiteralPath $LicenseFile -Encoding UTF8

$Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestOutput -Encoding UTF8
$Placeholder = $Manifest.assets | Where-Object { $_.size -le 0 -or $_.sha256 -eq ("0" * 64) }
if ($Placeholder) { throw "Release manifest still contains placeholder asset metadata" }

$BundleZip = Join-Path $OutputRoot "nuoyan-windows-standard-assets-$ReleaseVersion.zip"
if (Test-Path $BundleZip) { Remove-Item $BundleZip -Force }
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $BundleZip -Force
Write-Host "Built: $BundleZip"
