# Architecture

## Hexagonal (Port/Adapter) Architecture

The service is structured in concentric layers. Inner layers know nothing about outer layers.

```
┌────────────────────────────────────────────────────────────────┐
│  Delivery  (FastAPI routers, RQ workers, Streamlit dashboard)  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Application  (Services — own transaction boundaries)   │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  Domain  (Pydantic models, custom exceptions)    │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │  Repositories  (data-access port)                │   │   │
│  │  └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Infrastructure adapters  (Postgres · Redis · MinIO …) │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

---

## Layer rules

### Domain (`app/domain/`)
- Pure Pydantic models: `User`, `Batch`, `Prediction`, `AuditLogEntry`
- Custom exceptions: `ServiceError`, `PermissionDenied`, `NotFound`, `LastAdminError`, `RelabelNotAllowed`, `InvalidStateTransition`
- **Zero** external imports — no SQLAlchemy, no FastAPI, no Redis

### Repository (`app/repositories/`)
- One class per aggregate: `UserRepo`, `BatchRepo`, `PredictionRepo`, `AuditRepo`
- Accepts `AsyncSession` in constructor; returns **domain models** only (never ORM objects)
- **Never** calls `session.commit()` — the service layer owns transaction boundaries
- **Never** raises HTTP exceptions — raises domain exceptions or lets DB exceptions propagate

### Service (`app/services/`)
- One class per aggregate: `UserService`, `BatchService`, `PredictionService`, `AuditService`
- Accepts `(db: AsyncSession, cache: CacheInvalidator)` in constructor
- **Owns** transaction boundaries via `async with self.db.begin():`
- Calls `cache.delete()` after every mutation
- Writes an audit entry inside the same transaction as the mutation
- **Never** imports FastAPI; **never** raises `HTTPException`

### API (`app/api/`)
- FastAPI routers with dependency injection (`Depends`)
- Translates service exceptions to `HTTPException` (try/except in every mutating route)
- Enforces Casbin RBAC on every protected route: `enforcer.enforce(role, endpoint, method)`
- Login rate limiter at middleware level (5 attempts / 60 s / IP, in-process)
- Response caching via `@cache(expire=N)` decorator (fastapi-cache2 + Redis backend)

### Infrastructure (`app/infra/`)
| Module | Responsibility |
|---|---|
| `vault.py` | HashiCorp Vault KV-v2 client; env-var fallback in DEV_MODE |
| `cache.py` | `CacheInvalidator` protocol + Redis and in-memory implementations |
| `blob.py` | MinIO adapter (upload, download, exists, presigned_url) |
| `queue.py` | RQ job enqueuer wrapper |
| `sftp_watcher.py` | Paramiko SFTP poller with idempotency check |
| `security.py` | Argon2id password hashing via pwdlib |

### Workers (`app/workers/`)
| Module | Responsibility |
|---|---|
| `inference_worker.py` | RQ job function; process-level singletons for model and blob; bridges async services via `asyncio.run()` |
| `sftp_ingest.py` | Async SFTP polling loop; delegates to `BatchService` and `ClassifyQueue` |

---

## Data flow — SFTP ingestion path

```
sftp-ingest (poll every 5 s)
  ├─ listdir SFTP /upload
  ├─ skip files in _seen set (idempotency)
  ├─ validate: .tiff/.tif, non-zero, ≤ 100 MB
  ├─ blob.upload("batches/{id}/original/{file}")       → MinIO
  ├─ BatchService.create_batch(file_count=N)           → Postgres + audit_log
  └─ ClassifyQueue.enqueue_classify(batch_id, key)    → Redis / RQ

RQ worker (dequeue classify job)
  ├─ blob.download(blob_key)                          ← MinIO
  ├─ predict(model, image_bytes)                       → (label, confidence, logits)
  ├─ draw_overlay(image_bytes, label, confidence)
  ├─ blob.upload("batches/{id}/overlay/{stem}.png")   → MinIO
  └─ _persist_async():
       ├─ BatchService.mark_processing()              → Postgres + audit_log
       ├─ PredictionService.save_prediction()         → Postgres + cache invalidation
       └─ BatchService.mark_done()                    → Postgres + audit_log
```

---

## Batch status machine

```
  pending ──► processing ──► done
     │              │
     └──────────────┴──► failed
```

`done` and `failed` are terminal. `mark_processing` / `mark_done` are idempotent for
multi-file batches — the first job to complete each transition wins; siblings catch
`InvalidStateTransition` and log a debug message.

---

## Caching strategy

| Cache key | TTL | Invalidated when |
|---|---|---|
| `user:me:{id}` | 120 s | Role change, user delete |
| `users:list` | 60 s | User create / role change / delete |
| `batches:list` | 60 s | Batch create / status transition |
| `batch:{id}` | 60 s | Status transition |
| `predictions:recent` | 30 s | New prediction, relabel |
| `predictions:batch:{id}` | 60 s | New prediction, relabel |

---

## Authorization model

Casbin PRBAC with a flat `p, sub, obj, act` model file.

```
# Admin — full access
p, admin, /users,            GET | POST
p, admin, /users/role,       PATCH
p, admin, /users/delete,     DELETE
p, admin, /batches,          GET
p, admin, /batches/detail,   GET
p, admin, /predictions/recent,  GET
p, admin, /predictions/batch,   GET
p, admin, /predictions/relabel, PATCH    # any confidence
p, admin, /upload,           POST
p, admin, /audit,            GET

# Reviewer — read + relabel + upload
p, reviewer, /batches,          GET
p, reviewer, /batches/detail,   GET
p, reviewer, /predictions/recent,  GET
p, reviewer, /predictions/batch,   GET
p, reviewer, /predictions/relabel, PATCH  # service enforces confidence < 0.7
p, reviewer, /upload,           POST

# Auditor — read-only
p, auditor, /batches,          GET
p, auditor, /batches/detail,   GET
p, auditor, /predictions/recent,  GET
p, auditor, /predictions/batch,   GET
p, auditor, /audit,            GET
```

Policies are seeded from `casbin/policy.csv` on first boot into the `casbin_rule` table.
New rules added after first boot must be inserted directly into the table followed by an
API restart (see RUNBOOK.md).

---

## Database schema

```sql
users
  id             VARCHAR(36)   PK
  email          VARCHAR(255)  UNIQUE, INDEX
  hashed_password VARCHAR(512)
  role           ENUM(admin, reviewer, auditor)   DEFAULT auditor
  is_active      BOOLEAN       DEFAULT TRUE
  created_at, updated_at  TIMESTAMPTZ

batches
  id             VARCHAR(36)   PK
  status         ENUM(pending, processing, done, failed)  DEFAULT pending
  file_count     INTEGER       DEFAULT 0
  created_at, updated_at  TIMESTAMPTZ
  INDEX(status), INDEX(created_at)

predictions
  id             VARCHAR(36)   PK
  batch_id       VARCHAR(36)   FK→batches(CASCADE)
  filename       VARCHAR(512)
  blob_key       VARCHAR(512)  -- MinIO path to original TIFF
  overlay_key    VARCHAR(512)  -- MinIO path to annotated PNG
  predicted_class VARCHAR(100)
  confidence     FLOAT
  relabeled_class VARCHAR(100) NULLABLE
  created_at     TIMESTAMPTZ
  INDEX(batch_id), INDEX(predicted_class)

audit_logs
  id             VARCHAR(36)   PK
  actor_id       VARCHAR(36)   FK→users(SET NULL) NULLABLE
  action         VARCHAR(100)  -- e.g. user_create, role_change, relabel
  target         VARCHAR(255)  -- e.g. user:uuid, prediction:uuid
  details        JSONB
  timestamp      TIMESTAMPTZ   INDEX
```

---

## Secret management

```
Production
  Vault KV-v2  path: secret/docclassifier
  Keys:  JWT_SECRET  MINIO_ACCESS_KEY  MINIO_SECRET_KEY  SFTP_USER  SFTP_PASSWORD

Dev (Docker Compose)
  vault-init container seeds the secrets at first boot
  App reads them via app.infra.vault.get_secret()

Local dev without Vault (DEV_MODE=1)
  Same key names resolved from environment variables
  Never set DEV_MODE=1 in production
```
