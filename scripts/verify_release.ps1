$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$PipAudit = Join-Path $ProjectRoot '.venv\Scripts\pip-audit.exe'

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Create .venv and install requirements-dev.txt first."
}
if (-not (Test-Path $PipAudit)) {
    throw "pip-audit not found. Run .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt first."
}

$checks = @(
    @{ Name = 'Compile application and tests'; Executable = $Python; Arguments = @('-m','compileall','-q','aurix','tests') },
    @{ Name = 'Run unit and regression tests'; Executable = $Python; Arguments = @('-m','unittest','discover','-s','tests','-v') },
    @{ Name = 'Ruff lint'; Executable = $Python; Arguments = @('-m','ruff','check','aurix','tests') },
    @{ Name = 'Ruff formatter check for Milestone 6 files'; Executable = $Python; Arguments = @('-m','ruff','format','--check','aurix/main.py','aurix/observability.py','tests/test_observability.py') },
    @{ Name = 'Dependency consistency'; Executable = $Python; Arguments = @('-m','pip','check') },
    @{ Name = 'Dependency vulnerability audit'; Executable = $PipAudit; Arguments = @('-r','requirements-dev.txt') }
)

foreach ($check in $checks) {
    Write-Host "`n=== $($check.Name) ===" -ForegroundColor Cyan
    $arguments = $check.Arguments
    & $check.Executable @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Check failed: $($check.Name) (exit code $LASTEXITCODE). Fix it before releasing."
    }
}

Write-Host "`n=== Git whitespace check ===" -ForegroundColor Cyan
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Unstaged Git whitespace check failed.' }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Staged Git whitespace check failed.' }

Write-Host "`nAll local release checks passed. Remote CI and live-service behavior must be checked separately." -ForegroundColor Green
