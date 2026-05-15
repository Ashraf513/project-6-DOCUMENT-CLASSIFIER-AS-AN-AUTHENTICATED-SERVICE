# Local Development & Testing Guide

## Prerequisites

- **Python 3.11+** (recommended: 3.11 or 3.12)
- **Git LFS** (for model weights tracking): `git lfs install`
- **Docker Desktop** (required for Postgres, Redis, MinIO, Vault, SFTP)
- **uv** package manager: `pip install uv`

---

## 1. Initial Setup (First Clone)

```powershell
# Clone with LFS
git clone <your-repo-url>
cd docclassifier-week6
git lfs pull  # downloads classifier.pt (~106 MB)

# Install dependencies into virtualenv
uv sync --frozen  # reads pyproject.toml, creates .venv

# Verify virtualenv is active
.venv\Scripts\Activate.ps1  # PowerShell
# or
.venv\Scripts\activate.bat  # CMD
```

---

## 2. Code Validation (No Docker Required)

Run the local test suite to verify code correctness:

```powershell
cd docclassifier-week6
python test_local.py
```

**Expected output (first run, no deps installed):**
```
=== Step 1: File Integrity ===
  [OK] All .py files compile successfully
  [OK] Syntax validation

=== Step 2: Dependency Check ===
  [FAIL] Dependencies: Missing packages: sqlalchemy, redis, hvac, minio, rq, paramiko, torch, torchvision. Run: uv sync --frozen
```

**After `uv sync --frozen`:**
All tests should **PASS** except:
- `[!] Model card: test_top1 0.6347 below threshold 0.82` — this is **expected** if your trained model's accuracy is below the production threshold. Either retrain the model to >0.82 top-1 or set `DEV_SKIP_MODEL_CHECK=1` in your environment to bypass during development.

**Non-critical warnings (OK):**
- Vault adapter test: raises RuntimeError (expected locally without Vault running)
- classifier.pt existence: missing if you haven't trained yet (skip in dev)

---

## 3. Full Stack Integration Test (Docker Required)

### 3.1 Start All Services

```powershell
docker compose up -d
```

**Service startup order:**
1. Infrastructure: `db`, `redis`, `minio`, `sftp`, `vault` (parallel)
2. One-shot init: `vault-init`, `minio-init`, `migrate` (sequential)
3. Application: `api` (waits for inits to succeed)
4. Workers: `worker`, `sftp-ingest` (wait for `api` healthy)

Check health:
```powershell
docker compose ps
# All services should show "Up" or "running"
```

### 3.2 Seed First Admin User

```powershell
docker compose run --rm api python scripts/seed_admin.py
```

Expected output:
```
[seed-admin] Admin created successfully.
             Email   : admin@example.com
             Password: Admin1234!
             → Login at http://localhost:8000/docs
```

### 3.3 Verify API Health

```powershell
curl http://localhost:8000/health
# {"status":"healthy","service":"document-classifier-api"}
```

Or open browser: http://localhost:8000/docs (Swagger UI)

### 3.4 Login & Obtain JWT

```powershell
$token = curl -s -X POST http://localhost:8000/auth/jwt/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin@example.com&password=Admin1234!" | jq -r .access_token

echo $token
```

### 3.5 Create a Reviewer User (Admin Only)

```powershell
curl -s -X POST http://localhost:8000/users/ `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"email":"reviewer@example.com","password":"Reviewer123!","role":"reviewer"}' | jq
```

Expected response: user object with `id`, `email`, `role: "reviewer"`

### 3.6 Test End-to-End Pipeline

**Option A: Drop a file via SFTP (full pipeline)**
```powershell
# Copy a golden test image into the SFTP upload folder
docker compose exec -T sftp sh -c 'cat > /home/scanner/upload/memo_000103.tif' `
  < app/classifier/eval/golden_images/memo_000103.tif

# Wait ~10 seconds, then poll for prediction
for ($i=1; $i -le 30; $i++) {
  $count = curl -s -H "Authorization: Bearer $token" `
    "http://localhost:8000/predictions/recent?limit=10" | jq '. | length'
  if ($count -gt 0) {
    Write-Host "✅ Prediction appeared after ${i}s"
    break
  }
  Start-Sleep -Seconds 1
  Write-Host "Waiting... ($i)"
}

# View the prediction
curl -s -H "Authorization: Bearer $token" `
  "http://localhost:8000/predictions/recent?limit=1" | jq '.[0] | {id, predicted_class, confidence}'
```

**Option B: Use the test script (full integration)**
```powershell
python test_api_integration.py
```
This script performs:
- Admin login
- User creation (reviewer, auditor)
- Role-based access tests (403 checks)
- Cache invalidation verification
- Audit log retrieval

---

## 4. Model Training & Golden Test

### 4.1 Train on Google Colab

1. Open the training notebook in Colab
2. Download RVL-CDIP dataset (requires academic license)
3. Fine-tune ConvNeXt-Tiny
4. Save `classifier.pt` and `model_card.json` to `app/classifier/models/`
5. Push weights via Git LFS: `git add classifier.pt && git commit -m "Add trained weights"`

### 4.2 Run Golden Test Locally (with model present)

```powershell
python app/classifier/eval/golden.py
```

Expected:
```
✅ All 50 golden images passed.
```

If mismatch:
```
❌ MISMATCH memo_000103.tif: expected memo / 0.821777, got memo / 0.823456
❌ 1/50 golden images failed.
```

**Fix:** Retrain or verify `golden_expected.json` matches your model's predictions.

---

## 5. Common Development Tasks

### 5.1 Run Specific Test Suite

```powershell
# Service layer tests (against local Postgres)
python test_services_integration.py

# API integration (requires Docker up)
python test_api_integration.py

# Cache infrastructure demo
python test_cache_infrastructure.py
```

### 5.2 Database Migrations

```powershell
# Generate new migration after models.py change
alembic revision --autogenerate -m "description"

# Apply migrations (inside running stack)
docker compose run --rm migrate

# Or locally (if Postgres running)
alembic upgrade head
```

### 5.3 Debug Workers

```powershell
# View worker logs
docker compose logs -f worker
docker compose logs -f sftp-ingest

# View RQ failed jobs
docker compose exec redis redis-cli
> rq info
> rq failed -A default

# Retry a failed job (by job ID)
docker compose exec worker rq job <job-id> --requeue
```

### 5.4 Clear Redis Cache

```powershell
docker compose exec redis redis-cli FLUSHDB
```

### 5.5 Reset Database (WARNING: deletes all data)

```powershell
docker compose down -v  # removes volumes (Postgres, Redis, MinIO data)
docker compose up -d
# Re-run migrations and seed admin
docker compose run --rm migrate
docker compose run --rm api python scripts/seed_admin.py
```

---

## 6. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'redis'` | Dependencies not installed | `uv sync --frozen` |
| `email-validator is not installed` | Pydantic email extra missing | `uv sync --frozen` (includes `pydantic[email]`) |
| `RuntimeError: Vault authentication failed` | Vault container down | `docker compose up vault` and wait for healthy |
| `RuntimeError: Classifier weights missing` | `classifier.pt` not pulled | `git lfs pull` or copy from training output |
| `test_top1 below threshold` | Model accuracy too low | Retrain or set `DEV_SKIP_MODEL_CHECK=1` in `.env` |
| `SQLAlchemy Error: table users does not exist` | Migrations not applied | `docker compose run --rm migrate` |
| `403 Forbidden` on `/users/` | Casbin policy not seeded | Check `casbin_rules` table exists; `vault-init` ran |
| SFTP drop not detected | `sftp-ingest` container down | `docker compose logs sftp-ingest`; check SFTP_HOST env |
| Job stuck in `processing` | Worker crashed mid-job | Check `rq failed`; retry job; fix worker exception |

### Environment Variables (`.env` file)

```bash
# Create .env from .env.example if missing
cp .env.example .env

# Required:
VAULT_TOKEN=root  # dev only — root token

# Optional overrides:
API_PORT=8000
MINIO_PORT=9000
VAULT_PORT=8200
SFTP_PORT=2222
CORS_ORIGINS=http://localhost:3000
JWT_LIFETIME_SECONDS=86400
DEV_SKIP_MODEL_CHECK=0  # set to 1 to bypass integrity checks
```

---

## 7. Performance Targets (Local Validation)

| Metric | Target | How to Measure |
|--------|--------|----------------|
| API `/health` response | < 50 ms | `curl -w '%{time_total}' -o /dev/null http://localhost:8000/health` |
| Cached `/batches` | < 10 ms | Call twice, compare second is faster (Redis hit) |
| Uncached `/batches` | < 200 ms | First call after cache clear |
| Inference per doc (CPU) | < 1.5 s | Worker log: `inference_done` timestamp delta |
| SFTP → API visible | < 15 s | Drop file → poll `/predictions/recent` until non-empty |

---

## 8. CI Parity Locally

Before pushing, run the full CI sequence locally:

```powershell
# 1. Lint
ruff check app/
mypy app/ --ignore-missing-imports

# 2. Build
docker build --target api -t docclassifier-api .

# 3. Golden test (with model)
python app/classifier/eval/golden.py

# 4. Full stack (bring up stack, run smoke test)
docker compose up --build --wait --wait-timeout 120
docker compose run --rm api python scripts/seed_admin.py
# ... copy TIFF, poll, verify ...
docker compose down --volumes
```

For faster iteration, use the unit test suite (`pytest`) and local `test_local.py` only.

---

## 9. Next Steps After Local Verification

- [ ] All `test_local.py` checks pass (ignoring dependency failures pre-install)
- [ ] `golden.py` passes (model accuracy >= threshold)
- [ ] Docker stack starts cleanly, all services healthy
- [ ] Admin can log in, create users via API
- [ ] SFTP drop produces prediction in API within 20s
- [ ] Reviewer can relabel a low-confidence prediction but NOT high-confidence
- [ ] Last admin demotion blocked with 400
- [ ] Cache invalidation verified (change role → GET /users reflects immediately)
- [ ] Audit log shows all actions with correct details JSON

✅ **You are ready for the final presentation.**
