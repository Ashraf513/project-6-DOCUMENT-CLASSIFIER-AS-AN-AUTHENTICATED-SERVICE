# ============================================================================
# Complete CI Test Suite - Document Classifier
# ============================================================================
# This script runs all tests locally before pushing to GitHub:
# 1. Lint (Ruff)
# 2. Type-check (MyPy)
# 3. Golden-set regression test (64 images)
# 4. Smoke test (full stack: SFTP → inference → API)

param(
    [switch]$SkipLint = $false,
    [switch]$SkipTypeCheck = $false,
    [switch]$SkipGolden = $false,
    [switch]$SkipSmoke = $false
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date
$testsPassed = 0
$testsFailed = 0
$testsSkipped = 0

function Write-Section {
    param([string]$Title)
    Write-Host "`n" -NoNewline
    Write-Host ("=" * 80) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 80) -ForegroundColor Cyan
}

function Write-Pass {
    param([string]$Message)
    Write-Host "✅ $Message" -ForegroundColor Green
    $script:testsPassed++
}

function Write-Fail {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
    $script:testsFailed++
}

function Write-Skip {
    param([string]$Message)
    Write-Host "⊘ $Message" -ForegroundColor Yellow
    $script:testsSkipped++
}

# Change to project directory
cd "g:\project-6-DOCUMENT-CLASSIFIER-AS-AN-AUTHENTICATED-SERVICE\docclassifier-week6"
Write-Host "Working directory: $(Get-Location)" -ForegroundColor Gray

# =============================================================================
# TEST 1: LINT (Ruff)
# =============================================================================

Write-Section "Test 1: LINT (Ruff)"

if ($SkipLint) {
    Write-Skip "Lint check skipped"
} else {
    Write-Host "Checking code style with Ruff..." -ForegroundColor Cyan
    uv run ruff check app/ streamlit-dashboard.py

    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Lint check passed"
    } else {
        Write-Fail "Lint check failed (see errors above)"
    }
}

# =============================================================================
# TEST 2: TYPE-CHECK (MyPy)
# =============================================================================

Write-Section "Test 2: TYPE-CHECK (MyPy)"

if ($SkipTypeCheck) {
    Write-Skip "Type-check skipped"
} else {
    Write-Host "Type-checking with MyPy..." -ForegroundColor Cyan
    uv run mypy app/ --ignore-missing-imports --config-file=mypy.ini 2>&1 | Tee-Object -Variable mypyOutput | Out-Null

    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Type-check passed"
    } else {
        # Count errors
        $errorCount = ($mypyOutput | Select-String "error:" | Measure-Object).Count
        Write-Fail "Type-check found $errorCount error(s) (see above)"
    }
}

# =============================================================================
# TEST 3: GOLDEN-SET (Model Regression)
# =============================================================================

Write-Section "Test 3: GOLDEN-SET (Model Regression - 64 images)"

if ($SkipGolden) {
    Write-Skip "Golden-set test skipped"
} else {
    Write-Host "Running 64-image regression test..." -ForegroundColor Cyan
    Write-Host "This loads the model and verifies 64 golden images..." -ForegroundColor Gray

    uv sync > $null 2>&1
    uv run python app/classifier/eval/golden.py

    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Golden-set test passed (all 64 images matched)"
    } else {
        Write-Fail "Golden-set test failed (image predictions don't match expected)"
    }
}

# =============================================================================
# TEST 4: SMOKE TEST (Full Stack)
# =============================================================================

Write-Section "Test 4: SMOKE TEST (Full Stack: SFTP → Inference → API)"

if ($SkipSmoke) {
    Write-Skip "Smoke test skipped"
} else {
    Write-Host "Starting full stack and running end-to-end test..." -ForegroundColor Cyan

    # Step 1: Start services
    Write-Host "`n[Step 1/5] Starting services..." -ForegroundColor Yellow
    docker compose up --build --wait --wait-timeout 180 api worker sftp-ingest > $null 2>&1

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Failed to start services"
        $script:testsFailed++
    } else {
        Write-Host "✓ Services started" -ForegroundColor Green

        # Step 2: Seed admin
        Write-Host "[Step 2/5] Seeding admin user..." -ForegroundColor Yellow
        docker compose run --rm --no-TTY --entrypoint python api scripts/seed_admin.py > $null 2>&1

        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to seed admin"
        } else {
            Write-Host "✓ Admin seeded" -ForegroundColor Green

            # Step 3: Login
            Write-Host "[Step 3/5] Logging in as admin..." -ForegroundColor Yellow
            $loginResponse = curl.exe -s -X POST "http://localhost:8000/auth/jwt/login" `
              -H "Content-Type: application/x-www-form-urlencoded" `
              -d "username=admin@example.com&password=Admin1234!"

            $token = ($loginResponse | ConvertFrom-Json).access_token

            if (-not $token) {
                Write-Fail "Login failed"
            } else {
                Write-Host "✓ Login successful" -ForegroundColor Green

                # Step 4: Upload TIFF
                Write-Host "[Step 4/5] Uploading TIFF to SFTP..." -ForegroundColor Yellow
                $tifPath = "app/classifier/eval/golden_images/memo_000103.tif"
                docker compose cp "$tifPath" "sftp:/home/scanner/upload/smoke_test.tif" > $null 2>&1

                if ($LASTEXITCODE -ne 0) {
                    Write-Fail "Failed to upload TIFF"
                } else {
                    Write-Host "✓ TIFF uploaded" -ForegroundColor Green

                    # Step 5: Wait for prediction
                    Write-Host "[Step 5/5] Waiting for prediction (max 30 seconds)..." -ForegroundColor Yellow
                    $found = $false

                    for ($i = 1; $i -le 30; $i++) {
                        Start-Sleep -Seconds 1
                        $predResponse = curl.exe -s -H "Authorization: Bearer $token" `
                          "http://localhost:8000/predictions/recent?limit=10"

                        if ($predResponse) {
                            try {
                                $preds = $predResponse | ConvertFrom-Json
                                $count = if ($preds -is [array]) { $preds.Count } elseif ($preds) { 1 } else { 0 }

                                if ($count -gt 0) {
                                    Write-Host "✓ Prediction appeared after ${i}s" -ForegroundColor Green
                                    Write-Host "  Label: $($preds[0].predicted_class)" -ForegroundColor Cyan
                                    Write-Host "  Confidence: $($preds[0].confidence)" -ForegroundColor Cyan
                                    $found = $true
                                    break
                                }
                            } catch { }
                        }
                    }

                    # Cleanup
                    Write-Host "`nCleaning up..." -ForegroundColor Yellow
                    docker compose down --volumes > $null 2>&1

                    if ($found) {
                        Write-Pass "Smoke test passed (full stack working)"
                    } else {
                        Write-Fail "Smoke test failed (no prediction within 30s)"
                    }
                }
            }
        }
    }
}

# =============================================================================
# SUMMARY
# =============================================================================

Write-Section "TEST SUMMARY"

$total = $testsPassed + $testsFailed + $testsSkipped
$elapsed = ((Get-Date) - $startTime).TotalSeconds

Write-Host "`nResults:" -ForegroundColor Cyan
Write-Host "  ✅ Passed:  $testsPassed" -ForegroundColor Green
Write-Host "  ❌ Failed:  $testsFailed" -ForegroundColor Red
Write-Host "  ⊘ Skipped: $testsSkipped" -ForegroundColor Yellow
Write-Host "  Total:   $total" -ForegroundColor Gray
Write-Host "`nTime: ${elapsed}s" -ForegroundColor Gray

if ($testsFailed -eq 0) {
    Write-Host "`n✅✅✅ ALL TESTS PASSED ✅✅✅" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n❌ $testsFailed TEST(S) FAILED" -ForegroundColor Red
    exit 1
}
