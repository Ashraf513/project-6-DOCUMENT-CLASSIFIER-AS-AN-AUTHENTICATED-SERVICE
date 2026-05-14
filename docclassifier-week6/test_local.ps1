# =============================================================================
# Local Test Runner — Document Classifier
# =============================================================================
# This PowerShell script runs the Python-based local test suite.
# It does NOT require Docker services (PostgreSQL/Redis/MinIO/Vault).
#
# Usage:
#   .\test_local.ps1
#
# Exit code: 0 = all passed, 1 = failures
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Document Classifier — Local Tests" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $ProjectRoot

try {
    # Run the Python test suite
    Write-Host "Running test_local.py..." -ForegroundColor White
    python test_local.py
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        Write-Host "" -ForegroundColor Green
        Write-Host "✅ All local tests completed successfully!" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "" -ForegroundColor Red
        Write-Host "❌ Some tests failed. Check output above." -ForegroundColor Red
        Write-Host ""
    }

    exit $exitCode
}
catch {
    Write-Host "`n❌ ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
