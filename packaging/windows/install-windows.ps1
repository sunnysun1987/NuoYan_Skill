[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:USERPROFILE\.codex\skills\nuoyan-skill-v2",
    [string]$AssetBundle = "",
    [string]$AssetRoot = "",
    [string]$SourcesConfig = "",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$SourceOrder = @("local", "mirror", "public")
$PackageRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$ExpectedRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $env:USERPROFILE ".codex\skills\nuoyan-skill-v2")
)
$ResolvedInstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
$StateRoot = Join-Path $ResolvedInstallRoot ".nuoyan"
$StatePath = Join-Path $StateRoot "install-state.json"
$ManagedBrowserRoot = Join-Path $StateRoot "ms-playwright"

function Write-Step {
    param([string]$Message)
    Write-Host "`n[Nuoyan] $Message" -ForegroundColor Cyan
}

function Stop-Install {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

function Invoke-Native {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

function Test-AssetFile {
    param([string]$Path, [long]$ExpectedSize, [string]$ExpectedSha256)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $Item = Get-Item -LiteralPath $Path
    if ($Item.Length -ne $ExpectedSize) { return $false }
    $ActualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return $ActualHash -eq $ExpectedSha256.ToLowerInvariant()
}

function Get-ConfigValue {
    param([object]$Config, [string]$Name, [object]$DefaultValue = $null)
    if (-not $Config) { return $DefaultValue }
    $Property = $Config.PSObject.Properties[$Name]
    if (-not $Property) { return $DefaultValue }
    return $Property.Value
}

function Expand-SourceValue {
    param([string]$Value, [object]$Config)
    $Expanded = $Value
    $MirrorBaseUrl = Get-ConfigValue $Config "mirror_base_url" ""
    $PublicBaseUrl = Get-ConfigValue $Config "public_release_base_url" ""
    if ($MirrorBaseUrl) {
        $Expanded = $Expanded.Replace('${NUOYAN_MIRROR_BASE_URL}', [string]$MirrorBaseUrl)
    }
    if ($PublicBaseUrl) {
        $Expanded = $Expanded.Replace('${NUOYAN_RELEASE_BASE_URL}', [string]$PublicBaseUrl)
    }
    return $Expanded
}

function Resolve-NuoyanAsset {
    param(
        [object]$Asset,
        [string[]]$LocalRoots,
        [object]$Config,
        [string]$DownloadRoot,
        [switch]$ReadOnly
    )
    $Attempts = @()
    foreach ($SourceType in $SourceOrder) {
        if ($SourceType -eq "local") {
            foreach ($Root in $LocalRoots) {
                if (-not $Root) { continue }
                $Candidate = Join-Path $Root ([string]$Asset.relative_path)
                $Valid = Test-AssetFile $Candidate ([long]$Asset.size) ([string]$Asset.sha256)
                $Attempts += [ordered]@{ source_type = "local"; location = $Candidate; valid = $Valid }
                if ($Valid) {
                    return [ordered]@{
                        id = [string]$Asset.id
                        path = $Candidate
                        source_type = "local"
                        sha256 = [string]$Asset.sha256
                        version = [string]$Asset.version
                        attempts = $Attempts
                    }
                }
            }
            continue
        }
        if ($ReadOnly) { continue }
        $AllowPublicFallback = Get-ConfigValue $Config "allow_public_fallback" $true
        if ($SourceType -eq "public" -and $AllowPublicFallback -eq $false) {
            continue
        }
        $Source = $Asset.sources | Where-Object { $_.type -eq $SourceType } | Select-Object -First 1
        if (-not $Source -or -not $Source.url) { continue }
        $Url = Expand-SourceValue ([string]$Source.url) $Config
        if ($Url.Contains('${')) { continue }
        $Destination = Join-Path $DownloadRoot ([string]$Asset.relative_path)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination
            $Valid = Test-AssetFile $Destination ([long]$Asset.size) ([string]$Asset.sha256)
            $Attempts += [ordered]@{ source_type = $SourceType; location = $Url; valid = $Valid }
            if ($Valid) {
                return [ordered]@{
                    id = [string]$Asset.id
                    path = $Destination
                    source_type = $SourceType
                    sha256 = [string]$Asset.sha256
                    version = [string]$Asset.version
                    attempts = $Attempts
                }
            }
            Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
        }
        catch {
            $Attempts += [ordered]@{ source_type = $SourceType; location = $Url; valid = $false; error = $_.Exception.Message }
        }
    }
    return [ordered]@{ id = [string]$Asset.id; path = ""; source_type = "missing"; attempts = $Attempts }
}

function Copy-SkillSource {
    param([string]$SourceRoot, [string]$TargetRoot)
    New-Item -ItemType Directory -Force -Path $TargetRoot | Out-Null
    foreach ($Name in @("SKILL.md", "README.md", "pyproject.toml", "install-windows.ps1")) {
        $Source = Join-Path $SourceRoot $Name
        if (Test-Path $Source) { Copy-Item $Source (Join-Path $TargetRoot $Name) -Force }
    }
    foreach ($Name in @("agents", "assets", "references", "scripts", "docs", "packaging", "audit")) {
        $Source = Join-Path $SourceRoot $Name
        if (-not (Test-Path $Source)) { continue }
        $Target = Join-Path $TargetRoot $Name
        if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
        Copy-Item $Source $Target -Recurse -Force
    }
}

if ($ResolvedInstallRoot -ne $ExpectedRoot) {
    Stop-Install "InstallRoot must be the standard Codex path: $ExpectedRoot"
}

$env:PLAYWRIGHT_BROWSERS_PATH = $ManagedBrowserRoot
if ($VerifyOnly) {
    Write-Step "VerifyOnly does not download or modify files"
    $VenvPython = Join-Path $ResolvedInstallRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) { Stop-Install "The isolated runtime does not exist: $VenvPython" }
    Write-Host "Codex must have Life Science Research, Browser, and Chrome enabled in its plugin manager."
    & $VenvPython -m ivd_research.cli doctor --profile standard --network --strict --json
    exit $LASTEXITCODE
}

$AssetCache = Join-Path $StateRoot "asset-cache"
New-Item -ItemType Directory -Force -Path $AssetCache | Out-Null
$BundleRoot = ""
if ($AssetBundle) {
    if (-not (Test-Path $AssetBundle -PathType Leaf)) { Stop-Install "AssetBundle not found: $AssetBundle" }
    $BundleRoot = Join-Path $AssetCache "bundle"
    if (Test-Path $BundleRoot) { Remove-Item $BundleRoot -Recurse -Force }
    Expand-Archive -LiteralPath $AssetBundle -DestinationPath $BundleRoot -Force
}

$LocalRoots = @($AssetRoot, $BundleRoot) | Where-Object { $_ }
$ManifestPath = ""
foreach ($Root in $LocalRoots) {
    foreach ($Name in @("manifest.standard.release.json", "manifest.standard.json")) {
        $Candidate = Join-Path $Root $Name
        if (Test-Path $Candidate) { $ManifestPath = $Candidate; break }
    }
    if ($ManifestPath) { break }
}
if (-not $ManifestPath) { $ManifestPath = Join-Path $PSScriptRoot "manifest.standard.json" }
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Config = $null
if ($SourcesConfig) {
    $Config = Get-Content -LiteralPath $SourcesConfig -Raw -Encoding UTF8 | ConvertFrom-Json
}
elseif (Test-Path (Join-Path $PSScriptRoot "sources.json")) {
    $Config = Get-Content -LiteralPath (Join-Path $PSScriptRoot "sources.json") -Raw -Encoding UTF8 | ConvertFrom-Json
}
else {
    $Config = [pscustomobject]@{ allow_public_fallback = $true }
}

$ResolvedAssets = @{}
$InstallRecords = @()
if ($Manifest.release_ready -eq $true) {
    foreach ($Asset in $Manifest.assets) {
        $Resolved = Resolve-NuoyanAsset $Asset $LocalRoots $Config $AssetCache
        if (-not $Resolved.path -and $Asset.required) {
            Stop-Install "Required asset is unavailable or failed checksum validation: $($Asset.id)"
        }
        if ($Resolved.path) {
            $ResolvedAssets[[string]$Asset.id] = $Resolved
            $InstallRecords += $Resolved
        }
    }
}

$BasePython = ""
$PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    $BasePython = (& $PythonLauncher.Source -3.13 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
}
if (-not $BasePython -and $ResolvedAssets.ContainsKey("python-runtime")) {
    Write-Step "Installing the bundled Python 3.13 runtime"
    Invoke-Native $ResolvedAssets["python-runtime"].path @(
        "/quiet", "InstallAllUsers=0", "Include_launcher=1", "Include_pip=1", "PrependPath=0"
    )
    $BasePython = Join-Path $env:LocalAppData "Programs\Python\Python313\python.exe"
}
if (-not $BasePython -or -not (Test-Path $BasePython)) {
    Stop-Install "Python 3.13 is unavailable. Use a release asset bundle or ask IT to install the approved runtime."
}

if ($PackageRoot -ne $ResolvedInstallRoot) {
    Write-Step "Installing the Skill files from the local release package"
    Copy-SkillSource $PackageRoot $ResolvedInstallRoot
}

$VenvPython = Join-Path $ResolvedInstallRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Step "Creating the isolated Nuoyan Python environment"
    Invoke-Native $BasePython @("-m", "venv", (Join-Path $ResolvedInstallRoot ".venv"))
}

if ($ResolvedAssets.ContainsKey("python-wheelhouse")) {
    $Wheelhouse = Join-Path $StateRoot "wheelhouse"
    if (Test-Path $Wheelhouse) { Remove-Item $Wheelhouse -Recurse -Force }
    Expand-Archive -LiteralPath $ResolvedAssets["python-wheelhouse"].path -DestinationPath $Wheelhouse -Force
    Invoke-Native $VenvPython @(
        "-m", "pip", "install", "--no-index", "--find-links", $Wheelhouse,
        "setuptools>=68", "wheel"
    )
    Invoke-Native $VenvPython @(
        "-m", "pip", "install", "--no-index", "--find-links", $Wheelhouse,
        "--no-build-isolation", "--editable", "${ResolvedInstallRoot}[browser,pdf,translation]"
    )
}
else {
    Write-Step "No release wheelhouse found; using the configured package index"
    Invoke-Native $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Native $VenvPython @("-m", "pip", "install", "--editable", "${ResolvedInstallRoot}[browser,pdf,translation]")
    $InstallRecords += [ordered]@{
        id = "python-wheelhouse"
        path = ""
        source_type = "public_package_index"
        sha256 = ""
        version = "resolved-by-pip"
        attempts = @()
    }
}

if ($ResolvedAssets.ContainsKey("playwright-chromium")) {
    Write-Step "Installing the bundled Playwright Chromium runtime"
    if (Test-Path $ManagedBrowserRoot) { Remove-Item $ManagedBrowserRoot -Recurse -Force }
    Expand-Archive -LiteralPath $ResolvedAssets["playwright-chromium"].path -DestinationPath $ManagedBrowserRoot -Force
}
else {
    Write-Step "No bundled Chromium found; using Playwright's configured download source"
    Invoke-Native $VenvPython @("-m", "playwright", "install", "chromium")
    $InstallRecords += [ordered]@{
        id = "playwright-chromium"
        path = $ManagedBrowserRoot
        source_type = "public_package_index"
        sha256 = ""
        version = "resolved-by-playwright"
        attempts = @()
    }
}

$TranslationArgs = @("-m", "ivd_research.cli", "setup-translation-engine", "--provider", "argos", "--json")
if ($ResolvedAssets.ContainsKey("argos-en-zh-model")) {
    $TranslationArgs += @("--model-path", $ResolvedAssets["argos-en-zh-model"].path)
}
Write-Step "Installing or checking the offline English-to-Chinese model"
Invoke-Native $VenvPython $TranslationArgs
if (-not $ResolvedAssets.ContainsKey("argos-en-zh-model")) {
    $InstallRecords += [ordered]@{
        id = "argos-en-zh-model"
        path = ""
        source_type = "public_package_index"
        sha256 = ""
        version = "resolved-by-argospm"
        attempts = @()
    }
}
if (-not $ResolvedAssets.ContainsKey("python-runtime")) {
    $InstallRecords += [ordered]@{
        id = "python-runtime"
        path = $BasePython
        source_type = "system"
        sha256 = ""
        version = "3.13"
        attempts = @()
    }
}

New-Item -ItemType Directory -Force -Path $StateRoot | Out-Null
$State = [ordered]@{
    installed_at = [DateTimeOffset]::Now.ToString("o")
    skill_version = "2.3.0"
    manifest_version = [string]$Manifest.manifest_version
    manifest_path = $ManifestPath
    assets = $InstallRecords
    failures = @()
}
$TemporaryState = "$StatePath.tmp"
$State | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $TemporaryState -Encoding UTF8
Move-Item -LiteralPath $TemporaryState -Destination $StatePath -Force

Write-Step "Running the strict standard-environment check"
Write-Host "Codex must have Life Science Research, Browser, and Chrome enabled in its plugin manager."
& $VenvPython -m ivd_research.cli doctor --profile standard --network --strict --json
exit $LASTEXITCODE
