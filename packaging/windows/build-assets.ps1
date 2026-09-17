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
$PythonCommand = Get-Command $PythonExe -ErrorAction Stop
$PythonExe = $PythonCommand.Source
$PythonPrefixArgs = @()
if ([System.IO.Path]::GetFileName($PythonExe).ToLowerInvariant() -eq "py.exe") {
    $PythonPrefixArgs = @("-3.13")
}

function Invoke-BuildPython {
    param([string[]]$Arguments)
    & $PythonExe @PythonPrefixArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed ($LASTEXITCODE): $PythonExe $($Arguments -join ' ')"
    }
}

foreach ($Path in @($StageRoot, $BundleRoot)) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

$Wheelhouse = Join-Path $StageRoot "wheelhouse"
New-Item -ItemType Directory -Force -Path $Wheelhouse | Out-Null
Invoke-BuildPython -Arguments @(
    "-m", "pip", "download", "--dest", $Wheelhouse,
    "${PackageRoot}[browser,pdf,translation]", "setuptools>=68", "wheel", "pip"
)
Invoke-BuildPython -Arguments @(
    "-m", "pip", "wheel", "--no-deps", "--wheel-dir", $Wheelhouse, $PackageRoot
)

$BrowserRoot = Join-Path $StageRoot "ms-playwright"
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowserRoot
Invoke-BuildPython -Arguments @("-m", "pip", "install", "playwright", "argostranslate")
Invoke-BuildPython -Arguments @("-m", "playwright", "install", "chromium")

if (-not $ArgosModelPath) {
    $ArgosModelPath = (Invoke-BuildPython -Arguments @(
        "-c",
        "import argostranslate.package as p; p.update_package_index(); x=next(x for x in p.get_available_packages() if x.from_code=='en' and x.to_code=='zh'); print(x.download())"
    ) | Select-Object -Last 1)
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
Python wheelhouse: each unmodified wheel retains its METADATA and bundled license files
Playwright: Apache-2.0; Chromium third-party notices remain in the browser distribution
Argos Translate software: MIT
Argos English-to-Chinese model 1.9: derived from OPUS-MT and licensed CC BY 4.0
Model authors: Jörg Tiedemann and Santhosh Thottingal
Model work: "OPUS-MT — Building open translation services for the World", EAMT 2020
License: https://creativecommons.org/licenses/by/4.0/
"@ | Set-Content -LiteralPath $LicenseFile -Encoding UTF8

$Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestOutput -Encoding UTF8
$Placeholder = $Manifest.assets | Where-Object { $_.size -le 0 -or $_.sha256 -eq ("0" * 64) }
if ($Placeholder) { throw "Release manifest still contains placeholder asset metadata" }

$BundleZip = Join-Path $OutputRoot "nuoyan-windows-standard-assets-$ReleaseVersion.zip"
if (Test-Path $BundleZip) { Remove-Item $BundleZip -Force }
Compress-Archive -Path (Join-Path $BundleRoot "*") -DestinationPath $BundleZip -Force
Write-Host "Built: $BundleZip"
