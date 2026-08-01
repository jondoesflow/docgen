# docgen one-shot setup for Windows.
#
#   .\setup.ps1          install docgen into .venv and smoke-test it
#   .\setup.ps1 -Dev     also install dev dependencies (pytest) and run the test suite
#
# Idempotent: safe to re-run; reuses the existing .venv.

param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$repo = $PSScriptRoot
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"

Write-Host "== docgen setup ==" -ForegroundColor Cyan

# 1. Find a suitable Python
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host "Python not found on PATH. Install Python 3.11+ from https://www.python.org and re-run." -ForegroundColor Red
    exit 1
}
$version = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$parts = $version.Split('.')
if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
    Write-Host "Python $version found, but docgen needs 3.11+." -ForegroundColor Red
    exit 1
}
Write-Host "Using Python $version"

# 2. Create the virtual environment if it does not exist
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment in .venv ..."
    & python -m venv (Join-Path $repo ".venv")
} else {
    Write-Host "Reusing existing .venv"
}

# 3. Install docgen (editable, so local changes take effect immediately)
Write-Host "Installing docgen and dependencies ..."
& $venvPython -m pip install --quiet --upgrade pip
if ($Dev) {
    & $venvPython -m pip install --quiet -e $repo --group dev
} else {
    & $venvPython -m pip install --quiet -e $repo
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "pip install failed." -ForegroundColor Red
    exit 1
}

# 4. Smoke test
$docgen = Join-Path $repo ".venv\Scripts\docgen.exe"
& $docgen --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "docgen smoke test failed." -ForegroundColor Red
    exit 1
}

# 5. Optionally run the test suite
if ($Dev) {
    Write-Host "Running test suite ..."
    & $venvPython -m pytest
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Tests failed." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "== docgen is ready ==" -ForegroundColor Green
Write-Host ""
Write-Host "Activate the environment in this shell:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Then generate a full offline doc set from a solution export:"
Write-Host "    docgen all MySolution.zip --no-llm -o out\"
Write-Host ""
Write-Host "Optional LLM narrative tier (drafts HLD prose, flow descriptions):"
Write-Host "    `$env:ANTHROPIC_API_KEY = '<your key>'"
Write-Host "    docgen all MySolution.zip -o out\"
Write-Host ""
Write-Host "Docs: README.md (quickstart) - docs\USAGE.md (full reference)"
