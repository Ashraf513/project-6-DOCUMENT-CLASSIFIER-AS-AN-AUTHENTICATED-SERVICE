# Document Classifier — Authenticated Microservice

An authenticated document-classification microservice that automatically categorises
scanned documents (invoices, resumes, letters, …) using a ConvNeXt-Tiny neural network
trained on the RVL-CDIP dataset. Documents arrive via SFTP or HTTP upload; results are
browsable through a REST API and a Streamlit dashboard.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [16 document classes](#16-document-classes)
3. [Prerequisites](#prerequisites)
4. [Quick start](#quick-start)
5. [First-time admin setup](#first-time-admin-setup)
6. [Using the Streamlit dashboard](#using-the-streamlit-dashboard)
7. [Using the REST API](#using-the-rest-api)
8. [Testing the SFTP pipeline](#testing-the-sftp-pipeline)
9. [HTTP upload](#http-upload)
10. [Development workflow](#development-workflow)
11. [Running tests](#running-tests)
12. [CI / CD](#ci--cd)
13. [Performance budgets and verification](#performance-budgets-and-verification)
14. [Troubleshooting](#troubleshooting)
15. [Service reference](#service-reference)

---

## Architecture overview

```
Scanner vendor
     │  TIFF via SFTP
     ▼
┌─────────┐    ┌──────────────┐    ┌────────┐
│  SFTP   │───▶│ sftp-ingest  │───▶│ MinIO  │
│ server  │    │   worker     │    │ (blobs)│
└─────────┘    └──────────────┘    └────┬───┘
                     │ enqueue            │ download
                     ▼                   ▼
               ┌──────────┐      ┌───────────────┐
               │  Redis   │─────▶│ inference     │
               │  (RQ)    │      │ worker        │
               └──────────┘      │ ConvNeXt-Tiny │
                                 └───────┬───────┘
                                         │ write prediction + overlay
                                         ▼
                                  ┌────────────┐
                                  │ PostgreSQL  │
                                  └─────┬──────┘
                                        │
                                  ┌─────▼──────┐
                                  │  FastAPI   │◀── authenticated users
                                  │   + cache  │    (JWT + Casbin RBAC)
                                  └─────┬──────┘
                                        │
                                  ┌─────▼──────┐
                                  │ Streamlit  │◀── browser dashboard
                                  │ dashboard  │
                                  └────────────┘
```

**Layer rules (hexagonal architecture)**

| Layer | Rule |
|---|---|
| Repository | Returns domain models only; never calls `session.commit()` |
| Service | Owns transaction boundaries (`async with db.begin()`); invalidates cache; writes audit log |
| API | Translates service exceptions to `HTTPException`; enforces Casbin policies |
| Infrastructure | Encapsulates external drivers (Minio, Redis, SFTP, Vault, RQ) |

---

## 16 document classes

| # | Class | Example |
|---|---|---|
| 0 | letter | Business correspondence |
| 1 | form | Fill-in forms |
| 2 | email | Printed emails |
| 3 | handwritten | Handwritten notes |
| 4 | advertisement | Flyers, ads |
| 5 | scientific report | Lab reports |
| 6 | scientific publication | Journal papers |
| 7 | specification | Technical specs |
| 8 | file folder | Folder cover sheets |
| 9 | news article | Newspaper clippings |
| 10 | budget | Financial tables |
| 11 | invoice | Bills |
| 12 | presentation | Slide printouts |
| 13 | questionnaire | Surveys |
| 14 | resume | CVs |
| 15 | memo | Internal memos |

Classification is **visual-layout only** — no OCR, no text extraction.

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Docker Desktop | 4.25 | Must include Compose V2 (`docker compose` not `docker-compose`) |
| Git | 2.40 | — |
| Git LFS | 3.4 | Model weights (`classifier.pt`, ~110 MB) are stored in LFS |
| Python | 3.11 | Only needed for local dev outside Docker |
| uv | 0.5 | Fast Python package manager; install with `pip install uv` |
| curl + jq | any | For API testing from the shell |

**Windows users:** all commands below use PowerShell syntax. Bash equivalents work on macOS/Linux.

---

## Quick start

```powershell
# 1. Clone (pulls model weights via Git LFS automatically)
git clone <repo-url>
cd docclassifier-week6

# 2. Copy and review environment file
#    Only VAULT_TOKEN is required; everything else has safe defaults.
cp .env.example .env

# 3. Start the full stack (first run builds images — takes 3-5 min)
docker compose up --build -d

# 4. Watch services come up
docker compose ps
```

All 9 core services + dashboard + pgAdmin start in dependency order:

1. **Infrastructure** (parallel): `db` `redis` `minio` `sftp` `vault`
2. **Init containers** (parallel, exit 0): `vault-init` `minio-init` `migrate`
3. **Application**: `api` (waits for inits), then `worker` `sftp-ingest` `dashboard` (wait for api healthy)
4. **Tools**: `pgadmin`

The API is ready when `docker compose ps` shows `api` as `(healthy)`.

**Service URLs after startup**

| Service | URL | Credentials |
|---|---|---|
| REST API | http://localhost:8000 | JWT (see below) |
| Swagger UI | http://localhost:8000/docs | — |
| Streamlit dashboard | http://localhost:8501 | same JWT credentials |
| MinIO console | http://localhost:9001 | `minioadmin` / `minioadmin` |
| Vault UI | http://localhost:8200 | Token from `.env` (`root`) |
| pgAdmin | http://localhost:5050 | `admin@admin.com` / `admin` |

---

## First-time admin setup

The API has no open registration endpoint. The first admin must be seeded once:

```powershell
docker compose run --rm --entrypoint python api scripts/seed_admin.py
```

Default credentials:
- **Email:** `admin@example.com`
- **Password:** `Admin1234!`

Override with env vars before running the command:
```powershell
$env:SEED_ADMIN_EMAIL    = "you@company.com"
$env:SEED_ADMIN_PASSWORD = "YourSecurePass!"
docker compose run --rm --entrypoint python api scripts/seed_admin.py
```

The script is idempotent — safe to run multiple times.

---

## Using the Streamlit dashboard

Open http://localhost:8501 in your browser.

**Sign in** using the sidebar with your admin credentials.

| Tab | Who sees it | What it does |
|---|---|---|
| Overview | Everyone | Metrics, class distribution chart, recent predictions table |
| Batches | Everyone | Filter by status, drill into batch predictions |
| Upload | Admin / Reviewer | Upload TIFF files directly from the browser |
| Review | Admin / Reviewer | Relabel low-confidence predictions |
| Audit | Admin / Auditor | Full audit log with action filter and search |
| Users | Admin only | List users, change roles, invite, delete |

**Invite a new user** (from the Users tab as admin):
1. Enter email and temporary password
2. Choose role: `reviewer` or `auditor`
3. Click **Create account**

The new user can sign in immediately and change their password via the API if needed.

---

## Using the REST API

### Authenticate

```powershell
$token = (curl.exe -s -X POST http://localhost:8000/auth/jwt/login `
  -H "Content-Type: application/x-www-form-urlencoded" `
  -d "username=admin@example.com&password=Admin1234!" `
  | ConvertFrom-Json).access_token
```

All subsequent requests use `-H "Authorization: Bearer $token"`.

### Core endpoints

```powershell
# Who am I
curl.exe -s http://localhost:8000/users/me `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# List all users (admin only)
curl.exe -s http://localhost:8000/users/ `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# Create a user (admin only)
curl.exe -s -X POST http://localhost:8000/users/ `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"email":"reviewer@co.com","password":"Pass1234!","role":"reviewer"}' `
  | ConvertFrom-Json

# Change a user's role (admin only)
curl.exe -s -X PATCH "http://localhost:8000/users/<user_id>/role" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"role":"auditor"}' | ConvertFrom-Json

# Delete a user (admin only)
curl.exe -s -X DELETE "http://localhost:8000/users/<user_id>" `
  -H "Authorization: Bearer $token"

# List batches
curl.exe -s http://localhost:8000/batches/ `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# Get a single batch
curl.exe -s "http://localhost:8000/batches/<batch_id>" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# Recent predictions
curl.exe -s "http://localhost:8000/predictions/recent?limit=10" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# Predictions for a batch
curl.exe -s "http://localhost:8000/predictions/batch/<batch_id>" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

# Relabel a prediction (reviewer: only confidence < 0.7; admin: any)
curl.exe -s -X PATCH "http://localhost:8000/predictions/<pred_id>/relabel" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"relabeled_class":"invoice"}' | ConvertFrom-Json

# Audit log (admin / auditor)
curl.exe -s "http://localhost:8000/audit/?limit=50" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json
```

Full interactive docs at http://localhost:8000/docs (Swagger UI with **Authorize** button).

---

## Testing the SFTP pipeline

Drop a TIFF into the SFTP watch folder and watch it appear in the API within seconds.

```powershell
# Option A — use a golden-set image (already in the repo)
docker compose cp `
  .\app\classifier\eval\golden_images\memo_000103.tif `
  sftp:/home/scanner/upload/test.tif

# Option B — create a synthetic TIFF with Pillow
docker compose exec api python -c "
from PIL import Image
img = Image.new('RGB', (800, 600), color=(180, 180, 180))
img.save('/tmp/synthetic.tiff', format='TIFF')
"
docker compose cp api:/tmp/synthetic.tiff ./synthetic.tiff
docker compose cp ./synthetic.tiff sftp:/home/scanner/upload/synthetic.tiff
```

Poll until the prediction appears (SFTP poll interval is 5 s):

```powershell
# Poll every second for up to 30 s
for ($i = 1; $i -le 30; $i++) {
    $count = (curl.exe -s "http://localhost:8000/predictions/recent?limit=5" `
      -H "Authorization: Bearer $token" | ConvertFrom-Json).Count
    if ($count -gt 0) { Write-Host "Prediction appeared after ${i}s"; break }
    Start-Sleep 1
}

# Show result
curl.exe -s "http://localhost:8000/predictions/recent?limit=1" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json
```

Follow worker logs in real time:

```powershell
docker compose logs -f worker sftp-ingest
```

## Run With Docker

```bash
cd docclassifier-week6
cp .env.example .env
docker compose up --build
```

When the stack is up:
- API docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

The compose file starts PostgreSQL, Redis, the migration job, the API, and the Streamlit dashboard. The worker scaffolds are still placeholders in the codebase, so they are not started yet.

## Simple Dashboard

This branch adds a Streamlit dashboard.

```bash
cd docclassifier-week6
streamlit run streamlit_dashboard.py
```

Use the sidebar to sign in with your API account. If the API is not ready yet, the page still shows a demo layout so you can keep working on the interface.

---

## HTTP upload

Upload TIFF files directly without SFTP (admin or reviewer only):

```powershell
# Single file
curl.exe -s -X POST http://localhost:8000/upload/ `
  -H "Authorization: Bearer $token" `
  -F "files=@.\path\to\document.tiff" | ConvertFrom-Json

# Multiple files as one batch
curl.exe -s -X POST http://localhost:8000/upload/ `
  -H "Authorization: Bearer $token" `
  -F "files=@.\doc1.tiff" `
  -F "files=@.\doc2.tiff" `
  -F "files=@.\doc3.tiff" | ConvertFrom-Json
```

Response:
```json
{
  "batch_id": "3b9c8f65-...",
  "file_count": 3,
  "request_id": "f6ec0260-...",
  "jobs": [
    { "filename": "doc1.tiff", "blob_key": "batches/.../original/doc1.tiff", "job_id": "..." },
    ...
  ]
}
```

---

## Development workflow

### Local setup (outside Docker)

```powershell
# Install all dependencies including dev tools
uv sync --group dev

# Run linting and type checks
uv run ruff check app/ streamlit-dashboard.py
uv run mypy app/ --ignore-missing-imports

# Run the dashboard locally (points to the Docker stack API)
uv run streamlit run streamlit-dashboard.py
```

### Rebuilding after code changes

```powershell
# Rebuild only the changed service (uses Docker layer cache — fast)
docker compose up --build -d api      # after changing app/api/
docker compose up --build -d worker   # after changing app/workers/inference_worker.py
docker compose up --build -d dashboard  # after changing streamlit-dashboard.py

# Rebuild all (full stack)
docker compose up --build -d
```

Dependencies (`pyproject.toml` / `uv.lock`) only reinstall when those files change — the `COPY . .` layer is always fast.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VAULT_TOKEN` | `root` | Vault dev-mode root token |
| `DEV_SKIP_MODEL_CHECK` | `0` | `1` = skip SHA-256 + accuracy check (dev without weights) |
| `API_PORT` | `8000` | Host port for the API |
| `DASHBOARD_PORT` | `8501` | Host port for the Streamlit dashboard |
| `PGADMIN_PORT` | `5050` | Host port for pgAdmin |
| `PGADMIN_EMAIL` | `admin@admin.com` | pgAdmin login |
| `PGADMIN_PASSWORD` | `admin` | pgAdmin password |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed CORS origins (comma-separated) |
| `JWT_LIFETIME_SECONDS` | `86400` | Token validity (seconds) |

All variables go in `.env` (not committed to git).

---

## Running tests

### Structural tests (no Docker needed)

```powershell
uv run python test_local.py
```

Validates: syntax, domain models, service contracts, RBAC policies, security scan, golden-set structure.

### Service-layer integration tests (PostgreSQL needed)

```powershell
# Set DATABASE_URL to a running Postgres instance
$env:DATABASE_URL = "postgresql+asyncpg://docclassifier:docclassifier_dev@localhost:5432/docclassifier"
uv run python test_services_integration.py
```

### Cache integration tests (Redis needed)

```powershell
uv run python test_cache_infrastructure.py
```

### Full API integration tests (full Docker stack needed)

```powershell
docker compose up -d   # stack must be running
uv run python test_api_integration.py
```

### Golden-set regression test (model weights + LFS needed)

```powershell
uv run python app/classifier/eval/golden.py
```

Runs the trained model over 64 reference images and compares every predicted class and confidence against `golden_expected.json`. Exits 1 on any mismatch.

### All checks before pushing

```powershell
uv run ruff check app/ streamlit-dashboard.py    # lint
uv run mypy app/ --ignore-missing-imports         # types
uv run python test_local.py                       # structure
uv run python app/classifier/eval/golden.py       # model regression
```

---

## CI / CD

GitHub Actions runs on every push to `main`, `dev`, or `services-amer`, and on all PRs to `main`.

| Job | Depends on | What it does |
|---|---|---|
| `lint` | — | Ruff + MyPy on the full codebase |
| `build` | — | Builds the `api` Docker image; layers cached with `type=gha` |
| `golden` | `build` | Runs `golden.py` against the trained model |
| `smoke` | `build` + `golden` | Starts core services, seeds admin, drops a TIFF via SFTP, asserts a prediction appears within 30 s with non-empty `predicted_class`, `confidence > 0`, and `overlay_key` present |

The smoke test only starts the services needed for the signal (`api`, `worker`, `sftp-ingest` and their dependencies). `dashboard` and `pgadmin` are excluded to keep the job fast.

---

## Performance budgets and verification

| Metric | Budget | Mechanism |
|---|---|---|
| API cached reads (p95) | **< 50 ms** | Redis TTL cache via `fastapi-cache2`; checked with `curl -w "%{time_total}"` |
| API uncached reads (p95) | **< 200 ms** | PostgreSQL index scans; first hit after cache flush |
| Inference per document (p95) | **< 1.0 s** | ConvNeXt-Tiny CPU forward pass; logged by the worker |
| End-to-end SFTP → prediction visible (p95) | **< 10 s** | SFTP poll 5 s + inference ~2 s + DB write ~0.1 s |

### Measuring API latency

```powershell
$token = "<your_jwt>"

# Warm the cache (first call — uncached)
$uncached = (Measure-Command {
    curl.exe -s "http://localhost:8000/batches/" `
      -H "Authorization: Bearer $token" | Out-Null
}).TotalMilliseconds
Write-Host "Uncached: ${uncached}ms"

# Cached read (second call — served from Redis)
$cached = (Measure-Command {
    curl.exe -s "http://localhost:8000/batches/" `
      -H "Authorization: Bearer $token" | Out-Null
}).TotalMilliseconds
Write-Host "Cached:   ${cached}ms"
```

Or with curl's built-in timer:
```powershell
# Uncached (flush Redis first)
docker compose exec redis redis-cli flushall
curl.exe -s -o NUL -w "uncached: %{time_total}s\n" `
  -H "Authorization: Bearer $token" http://localhost:8000/batches/

# Cached (same endpoint, second hit)
curl.exe -s -o NUL -w "cached:   %{time_total}s\n" `
  -H "Authorization: Bearer $token" http://localhost:8000/batches/
```

### Measuring inference latency

Inference time is logged by the worker for every job:

```powershell
docker compose logs worker | Select-String "inference_done"
# inference_done label=memo confidence=0.8321
```

To time a single document end-to-end:

```powershell
$start = Get-Date
docker compose cp .\app\classifier\eval\golden_images\memo_000103.tif `
  sftp:/home/scanner/upload/latency_test.tif
# Poll until prediction appears
while ((curl.exe -s "http://localhost:8000/predictions/recent?limit=5" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json |
  Where-Object { $_.filename -eq "latency_test.tif" }).Count -eq 0) {
    Start-Sleep -Milliseconds 500
}
$elapsed = ((Get-Date) - $start).TotalSeconds
Write-Host "End-to-end: ${elapsed}s"
```

---

## Troubleshooting

### API returns 403 Forbidden on a new endpoint

The Casbin policy table is seeded once at first boot. If you added a new endpoint after the initial seed, insert the rule directly:

```powershell
docker compose exec db psql -U docclassifier -d docclassifier -c "
INSERT INTO casbin_rule (ptype, v0, v1, v2)
VALUES ('p', 'admin', '/your/endpoint', 'GET')
ON CONFLICT DO NOTHING;"
docker compose restart api
```

### Batch stuck in `processing`

A worker job failed after `mark_processing` ran. Check logs:

```powershell
docker compose logs worker --tail=50
docker compose exec redis redis-cli llen rq:queue:failed
```

Reset the stuck batch:

```powershell
docker compose exec db psql -U docclassifier -d docclassifier -c "
UPDATE batches SET status='failed' WHERE status='processing';"
```

### Worker not picking up jobs

Verify the worker connects to Redis (the `RQ_REDIS_URL` env var must be set):

```powershell
docker compose exec redis redis-cli llen rq:queue:default  # should be 0 when idle
docker compose logs worker --tail=20
```

### Model integrity check fails at startup

`DEV_SKIP_MODEL_CHECK=1` bypasses the SHA-256 and accuracy checks for local development without trained weights:

```powershell
# In .env
DEV_SKIP_MODEL_CHECK=1
docker compose up --build -d api worker
```

Never set this in production.

### Can't see dropdown options in the dashboard

Streamlit components follow the OS colour scheme. If dark mode makes dropdowns invisible, the `.streamlit/config.toml` sets `backgroundColor = "#ffffff"` which should force light mode. Restart the dashboard:

```powershell
docker compose restart dashboard
# or locally:
uv run streamlit run streamlit-dashboard.py
```

### Vault token expired

The dev-mode Vault stores all secrets in memory. If the vault container restarts, secrets are lost. The `vault-init` container re-seeds them automatically when `docker compose up` is run. If services fail with "Vault authentication failed", restart the full stack:

```powershell
docker compose down && docker compose up -d
```

---

## Service reference

### Docker Compose services

| Service | Image | Port | Role |
|---|---|---|---|
| `db` | postgres:16-alpine | internal | PostgreSQL 16 |
| `redis` | redis:7-alpine | internal | Cache + RQ message queue |
| `minio` | minio/minio | 9000, 9001 | S3-compatible blob storage |
| `sftp` | atmoz/sftp | 2222 | Scanner vendor drop zone |
| `vault` | hashicorp/vault | 8200 | Secret manager (dev mode) |
| `vault-init` | hashicorp/vault | — | One-shot secret seeder |
| `minio-init` | minio/mc | — | One-shot bucket creator |
| `migrate` | (project) | — | One-shot Alembic migration runner |
| `api` | (project) | 8000 | FastAPI server |
| `worker` | (project) | — | RQ inference worker |
| `sftp-ingest` | (project) | — | SFTP poller + enqueuer |
| `dashboard` | (project) | 8501 | Streamlit dashboard |
| `pgadmin` | dpage/pgadmin4 | 5050 | Database admin UI |

### pgAdmin — connect to the database

1. Open http://localhost:5050
2. Login: `admin@admin.com` / `admin`
3. Right-click **Servers** → **Register** → **Server**
4. **General:** Name = `docclassifier`
5. **Connection:** Host = `db`, Port = `5432`, Database = `docclassifier`, User = `docclassifier`, Password = `docclassifier_dev`

### Role permissions matrix

| Endpoint | Admin | Reviewer | Auditor |
|---|---|---|---|
| `GET /users/me` | ✅ | ✅ | ✅ |
| `GET /users/` | ✅ | ❌ | ❌ |
| `POST /users/` | ✅ | ❌ | ❌ |
| `PATCH /users/{id}/role` | ✅ | ❌ | ❌ |
| `DELETE /users/{id}` | ✅ | ❌ | ❌ |
| `GET /batches/` | ✅ | ✅ | ✅ |
| `GET /batches/{id}` | ✅ | ✅ | ✅ |
| `POST /upload/` | ✅ | ✅ | ❌ |
| `GET /predictions/recent` | ✅ | ✅ | ✅ |
| `GET /predictions/batch/{id}` | ✅ | ✅ | ✅ |
| `PATCH /predictions/{id}/relabel` | ✅ any confidence | ✅ confidence < 0.7 only | ❌ |
| `GET /audit/` | ✅ | ❌ | ✅ |

### Required tools for development

```powershell
# Docker Desktop (includes Compose V2)
# https://www.docker.com/products/docker-desktop/

# Git LFS
git lfs install

# uv (Python package manager)
pip install uv

# Verify everything is available
docker compose version   # should show v2.x
git lfs version
uv --version
```
