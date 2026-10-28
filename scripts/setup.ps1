# One-time setup. From the project folder:  .\scripts\setup.ps1
# Creates .venv, installs the dependencies and creates .env from .env.example if missing.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    Write-Host 'Creating virtual environment (.venv)...' -ForegroundColor Cyan
    py -3 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Install Python 3.10 or newer from python.org.' }
}

Write-Host 'Installing dependencies...' -ForegroundColor Cyan
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed (PyAudio is the usual cause; see docs/TROUBLESHOOTING.md).' }

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env - open it and set AI_API_KEY.' -ForegroundColor Yellow
}
Write-Host "`nSetup complete. Start AURIX with:  .\scripts\run.ps1" -ForegroundColor Green
