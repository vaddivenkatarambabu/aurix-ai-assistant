# Run every local quality gate. From the project folder:  .\scripts\verify_release.ps1
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    throw "Virtual-environment Python not found at $Python. Run .\scripts\setup.ps1 first."
}

$PythonVersionText = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine the virtual-environment Python version.' }
$PythonVersion = [version]$PythonVersionText

$checks = @(
    @{ Name = 'Compile application, tests and scripts'; Arguments = @('-m','compileall','-q','aurix','tests','scripts') },
    @{ Name = 'Run unit and regression tests'; Arguments = @('-m','unittest','discover','-s','tests','-v') },
    @{ Name = 'Ruff lint'; Arguments = @('-m','ruff','check','aurix','tests','scripts') },
    @{ Name = 'Ruff format check'; Arguments = @('-m','ruff','format','--check','aurix','tests','scripts') },
    @{ Name = 'Dependency consistency'; Arguments = @('-m','pip','check') }
)

if ($PythonVersion -ge [version]'3.11') {
    Write-Host "`n=== Install security audit tool ===" -ForegroundColor Cyan
    & $Python -m pip install -r (Join-Path $ProjectRoot 'requirements-security.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Could not install the security audit tool.' }
    $checks += @{ Name = 'Dependency vulnerability audit'; Arguments = @('-m','pip_audit','-r','requirements-dev.txt') }
} else {
    Write-Host "`nSkipping pip-audit under Python $PythonVersionText. The patched filelock release requires Python 3.11+; CI runs the security audit with Python 3.13." -ForegroundColor Yellow
}

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
