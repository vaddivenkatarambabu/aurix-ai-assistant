# Run every local quality gate. From the project folder:  .\scripts\verify_release.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Run .\scripts\setup.ps1 first."
}

$checks = @(
    @{ Name = 'Compile application, tests and scripts'; Arguments = @('-m','compileall','-q','aurix','tests','scripts') },
    @{ Name = 'Run unit and regression tests'; Arguments = @('-m','unittest','discover','-s','tests','-v') },
    @{ Name = 'Ruff lint'; Arguments = @('-m','ruff','check','aurix','tests','scripts') },
    @{ Name = 'Ruff format check'; Arguments = @('-m','ruff','format','--check','aurix','tests','scripts') },
    @{ Name = 'Dependency consistency'; Arguments = @('-m','pip','check') },
    @{ Name = 'Dependency vulnerability audit'; Arguments = @('-m','pip_audit','-r','requirements-dev.txt') }
)

foreach ($check in $checks) {
    Write-Host "`n=== $($check.Name) ===" -ForegroundColor Cyan
    $arguments = $check.Arguments
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Check failed: $($check.Name) (exit code $LASTEXITCODE). Fix it before releasing."
    }
}

if (Test-Path (Join-Path $ProjectRoot '.git')) {
    Write-Host "`n=== Git whitespace check ===" -ForegroundColor Cyan
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Unstaged Git whitespace check failed.' }
    git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'Staged Git whitespace check failed.' }
}

Write-Host "`nAll local checks passed. Remote CI and live-service behavior must be checked separately." -ForegroundColor Green
