# Architecture — Document Classifier Service

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                     External World                       │
│                                                          │
│  Scanner Vendor          Browser / API Client            │
│       │                        │                         │
│       │ SFTP (port 2222)       │ HTTP (port 8000)        │
└───────┼────────────────────────┼─────────────────────────┘
        │                        │
        ▼                        ▼
┌───────────────┐    ┌───────────────────────┐
│  SFTP Server  │    │     FastAPI (api)      │
│  (atmoz/sftp) │    │  JWT + Casbin RBAC     │
└───────┬───────┘    └──────────┬────────────┘
        │                       │
        │ poll every 5 s        │ async SQL
        ▼                       ▼
┌───────────────┐    ┌──────────────────────┐
│  sftp-ingest  │    │    PostgreSQL 16      │
│   worker      │    │    (db)              │
└──────┬────────┘    └──────────────────────┘
       │ upload TIFF                │
       ▼         enqueue job        │
┌──────────────┐ ──────────────► ┌─────────────────────┐
│  MinIO       │                 │  Redis Queue (RQ)   │
│  (blob store)│ ◄─── overlay    └──────────┬──────────┘
└──────────────┘       PNG                  │ dequeue
                                            ▼
                                ┌──────────────────────┐
                                │  inference worker    │
                                │  (ConvNeXt + torch)  │
                                └──────────────────────┘
                                            │
                              ┌─────────────┼──────────────┐
                              │ Vault       │ Redis        │
                              │ (secrets)   │ (cache)      │
                              └─────────────┴──────────────┘
```

---

## Layer Rules (enforced in code review)

```
app/api/routers/   HTTP only — parse request, call service, return response
                   ✗ No SQL   ✗ No business logic   ✗ No cache writes
       ↓
app/services/      Business logic — owns transactions and cache invalidation
                   ✗ No HTTP errors   ✗ No direct SQL
       ↓
app/repositories/  Database access only — SQL queries, return domain models
                   ✗ No HTTP errors   ✗ No cache   ✓ ORM imports allowed
       ↓
app/db/models.py   SQLAlchemy ORM definitions — imported only by repositories
```

**Domain models** (`app/domain/`) are Pydantic classes that flow between all layers.
They carry data but contain no SQL or HTTP logic.

**Infra adapters** (`app/infra/`) wrap external services (Vault, MinIO, Redis, SFTP).
They are the only code that knows the external service's API.

---

## Service Boot Order

```
Step 1 (parallel):   db · redis · minio · sftp · vault
Step 2 (parallel):   vault-init · minio-init · migrate
Step 3:              api          (waits for all inits + migrate)
Step 4 (parallel):   worker · sftp-ingest   (wait for api healthy)
```

`vault-init` seeds secrets into Vault KV v2.
`minio-init` creates the `documents` bucket.
`migrate` runs `alembic upgrade head` and exits 0.
`api` starts only after all three exit successfully.

---

## Data Flow: Document Classification

```
1. Scanner drops TIFF into SFTP /upload/

2. sftp-ingest polls SFTP every 5 s
   → validates: not zero-byte, must be .tiff, file size < limit
   → uploads original to MinIO: batches/{batch_id}/original/{file}.tiff
   → creates Batch row in Postgres (status=pending)
   → enqueues RQ job: {"batch_id": "...", "blob_key": "..."}

3. inference worker dequeues job
   → downloads TIFF from MinIO
   → runs ConvNeXt Tiny → (predicted_class, confidence)
   → draws overlay PNG, uploads to MinIO: batches/{batch_id}/overlay/{file}.png
   → writes Prediction row to Postgres
   → updates Batch status → done
   → deletes stale Redis cache keys

4. API user calls GET /batches/{id}
   → cache hit (Redis) or DB query
   → returns batch + prediction list as JSON
```

---

## Authentication and Authorization

```
Login (POST /auth/jwt/login):
  client sends email + password
  → fastapi-users verifies Argon2id hash
  → returns signed JWT (secret from Vault)

Subsequent requests:
  client sends: Authorization: Bearer <token>
  → fastapi-users decodes JWT, loads User
  → Casbin enforces: enforcer.enforce(role, resource, method)
  → if denied → 403 Forbidden

Casbin policy (casbin/policy.csv):
  p, admin,    /users,          GET
  p, admin,    /users,          POST
  p, admin,    /audit,          GET
  p, reviewer, /batches/detail, GET
  p, reviewer, /predictions,    PATCH
  ... (stored in DB via SQLAlchemy adapter)
```

---

## Secret Management

All runtime secrets are stored in HashiCorp Vault KV v2 at path `secret/docclassifier`:

| Secret | Used By |
|--------|---------|
| `JWT_SECRET` | fastapi-users JWT signing |
| `MINIO_ACCESS_KEY` | worker, sftp-ingest |
| `MINIO_SECRET_KEY` | worker, sftp-ingest |
| `SFTP_USER` | sftp-ingest |
| `SFTP_PASSWORD` | sftp-ingest |

The `.env` file holds only: `VAULT_TOKEN` and port numbers. Never application secrets.

---

## Docker Images

| Image (build target) | Base | Torch | Size (approx) |
|---|---|---|---|
| `api` | python:3.11-slim-bookworm | No | ~250 MB |
| `worker` | python:3.11-slim-bookworm | Yes (CPU-only) | ~900 MB |
| `sftp-ingest` | python:3.11-slim-bookworm | No | ~250 MB |
| `migrate` | python:3.11-slim-bookworm | No | ~250 MB |

All four targets share a single `Dockerfile` with 8 stages. The `deps-api` stage is built once
and reused by `api`, `sftp-ingest`, and `migrate`, saving ~3× install time on every build.

---

## Key Technology Choices

| Decision | Choice | Reason |
|---|---|---|
| Web framework | FastAPI | Async, auto-docs, Pydantic integration |
| Auth library | fastapi-users 15+ | Production-grade JWT + user management |
| Permission model | Casbin RBAC | Policy stored in DB, auditable, flexible |
| Job queue | RQ (Redis Queue) | Simple, no broker config, Redis already present |
| Blob storage | MinIO | S3-compatible, self-hosted, same API as AWS S3 |
| Secret store | HashiCorp Vault | No secrets in code or `.env` |
| ML backbone | ConvNeXt Tiny | p95 < 1s on CPU, >85% top-1 on RVL-CDIP |
| Package manager | uv | 10–100× faster than pip, deterministic lockfile |
| DB migrations | Alembic | Standard for SQLAlchemy async projects |

See [DECISIONS.md](DECISIONS.md) for detailed rationale behind each choice.
