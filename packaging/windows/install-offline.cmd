@echo off
setlocal

set "PACKAGE_ROOT=%~dp0nuoyan-skill-v2"
set "ASSET_BUNDLE=%~dp0nuoyan-windows-standard-assets-2.3.0.zip"

if not exist "%PACKAGE_ROOT%\install-windows.ps1" (
  echo Nuoyan source package is missing: %PACKAGE_ROOT%
  pause
  exit /b 1
)

if not exist "%ASSET_BUNDLE%" (
  echo Nuoyan offline asset bundle is missing: %ASSET_BUNDLE%
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_ROOT%\install-windows.ps1" -AssetBundle "%ASSET_BUNDLE%"
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
  echo Nuoyan installation and strict environment check completed.
) else (
  echo Nuoyan installation or environment check failed with exit code %EXIT_CODE%.
  echo Review the output above and provide it to Codex or IT.
)
pause
exit /b %EXIT_CODE%
