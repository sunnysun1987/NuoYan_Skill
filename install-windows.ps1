[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:USERPROFILE\.codex\skills\nuoyan-skill-v2",
    [string]$RepositoryUrl = "https://github.com/sunnysun1987/NuoYan_Skill.git",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

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
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

$ExpectedRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $env:USERPROFILE ".codex\skills\nuoyan-skill-v2")
)
$ResolvedInstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
if ($ResolvedInstallRoot -ne $ExpectedRoot) {
    Stop-Install "InstallRoot must be the standard Codex path: $ExpectedRoot"
}

if (-not $VerifyOnly) {
    Write-Step "Checking Git for Windows and Python 3.11"
    $GitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
    if (-not $GitCommand) {
        Stop-Install "Git for Windows is required. Ask IT to install it, then rerun this script."
    }
    $PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $PythonLauncher) {
        Stop-Install "Python 3.11 (64-bit, python.org build) is required. Ask IT to install it with the py launcher."
    }
    & $PythonLauncher.Source -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Python 3.11 was not found by the Windows py launcher."
    }

    Write-Step "Installing or fast-forwarding the skill repository"
    if (Test-Path (Join-Path $ResolvedInstallRoot ".git")) {
        Invoke-Native $GitCommand.Source @("-C", $ResolvedInstallRoot, "pull", "--ff-only")
    }
    elseif (Test-Path $ResolvedInstallRoot) {
        Stop-Install "The standard install directory exists but is not a Git checkout: $ResolvedInstallRoot. Back it up and ask IT to reinstall."
    }
    else {
        $SkillsRoot = Split-Path -Parent $ResolvedInstallRoot
        New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
        Invoke-Native $GitCommand.Source @("clone", $RepositoryUrl, $ResolvedInstallRoot)
    }

    Write-Step "Creating the isolated Nuoyan Python environment"
    $VenvPython = Join-Path $ResolvedInstallRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $VenvPython)) {
        Invoke-Native $PythonLauncher.Source @("-3.11", "-m", "venv", (Join-Path $ResolvedInstallRoot ".venv"))
    }
    Invoke-Native $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-Native $VenvPython @(
        "-m", "pip", "install", "--editable", "${ResolvedInstallRoot}[browser,pdf,translation]"
    )

    Write-Step "Installing the managed Chromium browser"
    Invoke-Native $VenvPython @("-m", "playwright", "install", "chromium")

    Write-Step "Installing or checking the offline English-to-Chinese model"
    Invoke-Native $VenvPython @(
        "-m", "ivd_research.cli", "setup-translation-engine", "--provider", "argos", "--json"
    )
}

$VenvPython = Join-Path $ResolvedInstallRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Stop-Install "The isolated runtime does not exist: $VenvPython. Rerun without -VerifyOnly."
}

Write-Step "Running the strict standard-environment check"
Write-Host "Codex must have Life Science Research, Browser, and Chrome enabled in its plugin manager."
& $VenvPython -m ivd_research.cli doctor --profile standard --network --strict --json
$DoctorExitCode = $LASTEXITCODE
if ($DoctorExitCode -ne 0) {
    Write-Warning "The Python runtime was installed, but the standard research environment is not ready. Read the failed checks above, enable missing Codex plugins in the app, restart Codex, and rerun this script with -VerifyOnly."
    exit $DoctorExitCode
}

Write-Host "`nNuoyan standard research environment is ready." -ForegroundColor Green
