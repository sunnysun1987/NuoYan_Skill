[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:USERPROFILE\.codex\skills\nuoyan-skill-v2",
    [string]$AssetBundle = "",
    [string]$AssetRoot = "",
    [string]$SourcesConfig = "",
    [switch]$VerifyOnly
)

$Installer = Join-Path $PSScriptRoot "packaging\windows\install-windows.ps1"
if (-not (Test-Path $Installer)) {
    throw "Packaged installer not found: $Installer"
}
& $Installer @PSBoundParameters
exit $LASTEXITCODE
