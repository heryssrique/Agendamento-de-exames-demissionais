<#
Regenerate backend wheelhouse for Python 3.11 (manylinux wheels).

Usage: Run this script in PowerShell (prefer WSL2 or Linux host for best compatibility):
  ./scripts/regenerate_wheels.ps1

The script will:
 - create backend/wheels if missing
 - try to download manylinux2014_x86_64 wheels (recommended)
 - if that fails, retry without --platform to let pip pick the best files
 - list the files downloaded
#>

Set-StrictMode -Version Latest

$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Push-Location $root\..\

if (-not (Test-Path "backend/wheels")) {
    New-Item -ItemType Directory -Path backend/wheels | Out-Null
}

Write-Host "Attempting to download wheels (manylinux2014_x86_64)..."
$cmd = "python -m pip download -r backend/requirements-prod.txt -d backend/wheels --platform manylinux2014_x86_64 --only-binary=:all: --implementation cp --abi cp311 -i https://pypi.org/simple"
$rc = & powershell -NoProfile -Command $cmd 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warning "First attempt failed (platform-specific). Falling back to a general binary-only download."
    $cmd2 = "python -m pip download -r backend/requirements-prod.txt -d backend/wheels --only-binary=:all: -i https://pypi.org/simple"
    & powershell -NoProfile -Command $cmd2
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Fallback download also failed. Inspect output above and adjust versions or run from a Linux/WSL environment."
        Pop-Location
        exit 1
    }
}

Write-Host "Download finished. Current wheel files:"
Get-ChildItem backend\wheels | Sort-Object Name | ForEach-Object { $_.Name }

Pop-Location