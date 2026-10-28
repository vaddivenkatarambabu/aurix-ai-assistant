# Start AURIX. From the project folder:  .\scripts\run.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw 'No .venv found. Run .\scripts\setup.ps1 first.'
}
& $Python -m aurix.main
