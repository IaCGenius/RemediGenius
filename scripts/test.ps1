$ErrorActionPreference = 'Stop'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $cePython = if (Test-Path '.venv/Scripts/python.exe') { '.venv/Scripts/python.exe' } else { 'python' }
    & $cePython tests/test_checks.py
    if ($LASTEXITCODE) { throw 'Rule cases failed' }
    & $cePython tests/test_results.py
    if ($LASTEXITCODE) { throw 'Result view failed' }
    & $cePython -m pytest -q tests
    if ($LASTEXITCODE) { throw 'Community tests failed' }
    & $cePython -m pytest -q modules/lambda-kiosk/tests
    if ($LASTEXITCODE) { throw 'Kiosk tests failed' }
} finally { Pop-Location }
