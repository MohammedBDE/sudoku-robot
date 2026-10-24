# Set up sudoku_robot on a Windows dev machine (simulation, tests, rendering
# -- no real arm). Run from the project root in PowerShell:
#
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1          create .venv-win if missing, install, verify
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Fresh   delete and recreate .venv-win first
#
# Uses .venv-win, NOT .venv: the committed .venv folder is the Raspberry Pi's
# Linux venv and can't run on Windows. Needs Python 3.13 (the "py" launcher
# is used to find it; override with -Python C:\path\to\python.exe).
param(
    [switch]$Fresh,
    [string]$Python = ""
)
$ErrorActionPreference = "Stop"
# Always operate on the project root (the folder above scripts\), wherever this is run from.
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py -3.13" } else { $Python = "python" }
}
$pyParts = $Python.Split(" ")
$pyExe = $pyParts[0]
$pyArgs = @($pyParts | Select-Object -Skip 1)

try {
    $version = & $pyExe @pyArgs -c "import sys; print('%d.%d' % sys.version_info[:2])"
} catch {
    Write-Error "Could not run '$Python'. Install Python 3.13 from python.org (tick 'Add to PATH')."
    exit 1
}
if ($version -ne "3.13") {
    Write-Warning "'$Python' is Python $version; requirements.txt is pinned for 3.13. Pinned wheels may not exist for $version."
}

if ($Fresh -and (Test-Path .venv-win)) {
    Write-Host "==> Removing existing .venv-win (-Fresh)"
    Remove-Item -Recurse -Force .venv-win
}
if (-not (Test-Path .venv-win\Scripts\python.exe)) {
    Write-Host "==> Creating .venv-win with $Python"
    & $pyExe @pyArgs -m venv .venv-win
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed"; exit 1 }
}

$venvPy = ".venv-win\Scripts\python.exe"
Write-Host "==> Installing pinned requirements"
& $venvPy -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Write-Error "pip upgrade failed"; exit 1 }
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Error "pip install -r requirements.txt failed (see above)"; exit 1 }

Write-Host "==> Verifying the environment"
& $venvPy scripts\verify_env.py
$status = $LASTEXITCODE
if ($status -ne 0) {
    Write-Host ""
    Write-Host "Setup finished, but verification FAILED -- see the FAIL lines above." -ForegroundColor Red
    exit $status
}
Write-Host ""
Write-Host "Done. Activate with:  .venv-win\Scripts\Activate.ps1"
