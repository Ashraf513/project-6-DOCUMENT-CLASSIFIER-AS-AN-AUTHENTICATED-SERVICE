# Testing Guide — Document Classifier

## Quick Start

Run all tests locally:

```powershell
cd g:\project-6-DOCUMENT-CLASSIFIER-AS-AN-AUTHENTICATED-SERVICE\docclassifier-week6
powershell -ExecutionPolicy Bypass .\run-all-tests.ps1
```

---

## Tests Overview

| # | Test | Time | What It Does | Status |
|---|------|------|-------------|--------|
| 1 | **Lint** | 30s | Code style check (Ruff) | ✅ |
| 2 | **Type-check** | 1m | Type annotations (MyPy) | ✅ |
| 3 | **Golden-set** | 2m | 64-image regression test | ✅ |
| 4 | **Smoke test** | 5m | Full stack (SFTP→API) | ✅ |
| **Total** | | **~8-10 min** | All tests | |

---

## Running Individual Tests

### Test 1: Lint Only

```powershell
uv run ruff check app/ streamlit-dashboard.py
```

**Pass criteria:** No output (zero errors)

### Test 2: Type-check Only

```powershell
uv run mypy app/ --ignore-missing-imports --config-file=mypy.ini
```

**Pass criteria:** `Success: no issues found`

### Test 3: Golden-set Only

```powershell
uv sync
uv run python app/classifier/eval/golden.py
```

**What it does:**
- Loads the ConvNeXt-Tiny model
- Runs 64 reference images through it
- Compares predictions against `golden_expected.json`
- All 64 must match (same label and confidence threshold)

**Pass criteria:** All images match expected predictions

### Test 4: Smoke Test Only

```powershell
# Skip lint, type-check, and golden tests
powershell -ExecutionPolicy Bypass .\run-all-tests.ps1 -SkipLint -SkipTypeCheck -SkipGolden
```

**What it does:**
1. Start full stack (api, worker, sftp-ingest, db, redis, minio, vault)
2. Seed admin user
3. Login and get JWT token
4. Upload TIFF to SFTP
5. Poll API until prediction appears (max 30s)
6. Verify prediction has all required fields
7. Cleanup

**Pass criteria:** Prediction appears within 30 seconds

---

## Command-line Options

```powershell
# Skip specific tests
.\run-all-tests.ps1 -SkipLint
.\run-all-tests.ps1 -SkipTypeCheck
.\run-all-tests.ps1 -SkipGolden
.\run-all-tests.ps1 -SkipSmoke

# Run only specific tests
.\run-all-tests.ps1 -SkipLint -SkipTypeCheck -SkipGolden  # Only smoke test
.\run-all-tests.ps1 -SkipSmoke                              # All except smoke test
```

---

## Expected Output

### ✅ Success (All Tests Passed)

```
✅ Lint check passed
✅ Type-check passed
✅ Golden-set test passed (all 64 images matched)
✅ Smoke test passed (full stack working)

================================================================================
  TEST SUMMARY
================================================================================

Results:
  ✅ Passed:  4
  ❌ Failed:  0
  ⊘ Skipped: 0
  Total:   4

Time: 487s

✅✅✅ ALL TESTS PASSED ✅✅✅
```

### ❌ Failure (One Test Failed)

```
================================================================================
  TEST SUMMARY
================================================================================

Results:
  ✅ Passed:  2
  ❌ Failed:  1
  ⊘ Skipped: 1
  Total:   4

Time: 125s

❌ 1 TEST(S) FAILED
```

---

## Troubleshooting

### Lint test fails
**Error:** Ruff found style issues
**Fix:** 
```powershell
uv run ruff check --fix app/ streamlit-dashboard.py
```

### Type-check fails
**Error:** MyPy found type annotation issues
**Fix:** Either:
1. Add proper type hints to the code
2. Add `# type: ignore` comments for known issues
3. Update `mypy.ini` to exclude the problematic module

### Golden-set test fails
**Error:** Image predictions don't match expected
**Possible causes:**
- Model weights changed (different weights file)
- Python version difference
- Pillow version difference
- **Expected:** This test should pass with the provided `classifier.pt`

### Smoke test fails
**Error:** Prediction doesn't appear within 30s
**Troubleshooting steps:**
```powershell
# Check if services are running
docker compose ps

# Check worker logs
docker compose logs worker --tail=50

# Check sftp-ingest logs
docker compose logs sftp-ingest --tail=30

# Check API logs
docker compose logs api --tail=20

# Cleanup after failure
docker compose down --volumes
```

---

## CI/CD Integration

These tests run automatically on GitHub Actions when you push to:
- `main`
- `dev`
- `services-amer`

Or on any pull request to `main`.

View results: https://github.com/Ashraf513/project-6-DOCUMENT-CLASSIFIER-AS-AN-AUTHENTICATED-SERVICE/actions

---

## Performance Notes

- **Lint** (Ruff): Checks 49 files, should be <1 min
- **Type-check** (MyPy): Checks types in all files, ~1 min
- **Golden-set**: Loads model (~2s), runs 64 inferences (~50s)
- **Smoke test**: Docker startup (~120s), SFTP/inference (~5s), polling (~10s)

Total for all tests: **~8-10 minutes** on a typical machine.

---

## Test Files Location

| File | Purpose |
|------|---------|
| `run-all-tests.ps1` | Main test runner script |
| `app/classifier/eval/golden.py` | Golden-set regression test |
| `app/classifier/eval/golden_expected.json` | Expected predictions (64 images) |
| `app/classifier/eval/golden_images/` | 64 reference TIFF files |
| `.github/workflows/ci.yml` | CI configuration for GitHub Actions |
| `mypy.ini` | MyPy type-checker configuration |

---

## Success Criteria

✅ **All tests must pass before pushing to main:**

- [ ] Lint (Ruff): 0 style errors
- [ ] Type-check (MyPy): 0 type errors
- [ ] Golden-set: All 64 images match
- [ ] Smoke test: Prediction within 30s

**Then push to GitHub:**
```powershell
git add .
git commit -m "test: all tests passing"
git push origin services-amer
```

CI will run the same tests on GitHub Actions.
