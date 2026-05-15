# Architecture Decision Records

Decisions are listed in the order they were made. Each record states the context,
the options considered, the choice, and the rationale.

---

## ADR-001 — Python + FastAPI for the API tier

**Context:** We need an async HTTP server for a document classification service with
JWT auth, RBAC, and Redis caching.

**Options considered:**
- Flask (sync, no native async, no DI)
- Django REST Framework (batteries-included but heavy; sync ORM complicates async)
- FastAPI (async-first, Pydantic integration, automatic OpenAPI docs, `Depends` DI)

**Decision:** FastAPI.

**Rationale:** Native async (uvicorn + asyncio) avoids blocking I/O on every DB/Redis
call. `Depends()` makes injecting session, cache, enforcer, and current user explicit
and testable. Auto-generated Swagger UI at `/docs` is a project requirement for
demonstrating the API to stakeholders.

---

## ADR-002 — SQLAlchemy 2.0 async + asyncpg for database access

**Context:** Multiple concurrent API requests and async workers must read/write
PostgreSQL without blocking the event loop.

**Options considered:**
- psycopg2 (sync only — blocks the loop)
- Tortoise ORM (async but limited ecosystem)
- SQLAlchemy 2.0 + asyncpg (mature, widely supported, compatible with Alembic)

**Decision:** SQLAlchemy 2.0 async with asyncpg driver.

**Rationale:** `AsyncSession` + `async with session.begin()` gives precise transaction
control. Alembic handles schema migrations with the same models. The sync `psycopg2`
driver is kept as a second dependency only for the Casbin SQLAlchemy adapter (which
has no async adapter) and for RQ workers that bridge to async via `asyncio.run()`.

---

## ADR-003 — Repository pattern (no Active Record)

**Context:** The service layer must be testable in isolation without a real database.

**Options considered:**
- Active Record (models expose save/delete — ORM objects leak into business logic)
- Repository pattern (data-access code in dedicated classes; service receives domain models)

**Decision:** Repository pattern with strict domain-model returns.

**Rationale:** Repos return Pydantic domain models (`User`, `Batch`, `Prediction`), not
ORM objects. This means the service layer has no SQLAlchemy imports and can be tested
with `InMemoryCacheInvalidator` and mock repos. Repos never commit — the service owns
the transaction — so partial failures are rolled back cleanly.

---

## ADR-004 — RQ (Redis Queue) over Celery for inference jobs

**Context:** SFTP-ingested documents must be classified asynchronously by a background
worker.

**Options considered:**
- Celery + RabbitMQ (powerful but complex; AMQP overkill for single-queue use-case)
- Celery + Redis (lighter, but Celery has complex config and its own serialisation)
- RQ (Redis Queue — minimalist; jobs are Python function references; simple CLI worker)

**Decision:** RQ with Redis.

**Rationale:** A single `default` queue with one worker process is all we need. RQ's
`rq worker` CLI starts in one line; `rq.Queue.enqueue()` in three. Job results are
stored in Redis with configurable TTLs. The `--with-scheduler` flag provides cron-like
scheduling without extra infrastructure.

---

## ADR-005 — MinIO for blob storage

**Context:** Original TIFF files and generated overlay PNGs must be stored durably and
served via presigned URLs without routing large files through the API container.

**Options considered:**
- Local filesystem (not portable between containers; no presigned URLs)
- AWS S3 (requires AWS account; adds cost and network dependency to local dev)
- MinIO (S3-compatible, self-hosted, runs in Docker, same SDK as S3)

**Decision:** MinIO.

**Rationale:** The minio-py SDK is API-compatible with boto3. Switching to S3 in
production requires only changing the endpoint URL — no code changes. Local dev has
zero cloud dependency. The 100 MB per-file cap is enforced in `BlobStorage.upload()`
to protect the blob store from oversized files.

---

## ADR-006 — Casbin for RBAC

**Context:** Three roles (admin, reviewer, auditor) with different permissions on every
endpoint. The access-control policy must be auditable and centrally maintainable.

**Options considered:**
- Hand-written if/else checks in each route (brittle, scattered, untestable)
- FastAPI-Users' built-in permission system (only supports active/superuser, not multi-role)
- Casbin (policy-file-driven RBAC; SQLAlchemy adapter persists policies to DB)

**Decision:** Casbin with the SQLAlchemy adapter.

**Rationale:** All permissions live in `casbin/policy.csv` — a single diff to review.
The `enforcer.enforce(role, endpoint, method)` call on each route is one line. The
SQLAlchemy adapter loads/saves policies to `casbin_rule` table so policies survive
restarts without needing the CSV file at runtime.

---

## ADR-007 — HashiCorp Vault for secret management

**Context:** JWT signing secrets, MinIO credentials, and SFTP credentials must never
be hard-coded or stored in environment files committed to git.

**Options considered:**
- `.env` file (convenient but easily leaked; not suitable for production)
- AWS Secrets Manager (cloud dependency; unavailable locally)
- HashiCorp Vault (self-hosted; KV-v2 store; dev mode works in Docker without setup)

**Decision:** Vault KV-v2 with a DEV_MODE env-var fallback.

**Rationale:** The `vault-init` container seeds all secrets at first boot. The app reads
them via `app.infra.vault.get_secret()`, which falls back to env vars when
`VAULT_ADDR` is unset (local dev without Docker). No secrets appear in any committed
file.

---

## ADR-008 — ConvNeXt-Tiny for document classification

**Context:** We need a model that classifies documents by visual layout across 16
classes (RVL-CDIP subset), running on CPU in production without a GPU.

**Options considered:**
- ResNet-50 (strong baseline but older architecture; less efficient per parameter)
- EfficientNet-B0 (good CPU efficiency; less pretrained support in torchvision)
- ConvNeXt-Tiny (modern convolutional, ImageNet-1K pretrained, ~28 M params, fast on CPU)
- ConvNeXt-Small (larger — ~50 M params; slower on CPU, marginal accuracy gain)
- Vision Transformer ViT-B/16 (attention-heavy; much slower on CPU)

**Decision:** ConvNeXt-Tiny.

**Rationale:** Achieves p95 inference < 1.0 s on a single CPU core after model warmup.
The 16-class head replaces the final `nn.Linear(768, 1000)` layer. Training used linear
probing for 20 epochs then partial unfreezing for 20 epochs; test_top1 = 63.5% on
RVL-CDIP's held-out split (the dataset is intentionally challenging — budget and
scientific-report classes are below 50%). The model card records SHA-256 of weights,
accuracy metrics, and environment metadata for reproducibility.

---

## ADR-009 — CPU-only PyTorch wheels

**Context:** The Docker image includes PyTorch (~500 MB with CUDA, ~120 MB CPU-only).
CI runners and production containers have no GPU.

**Decision:** Pin `torch` and `torchvision` to the `https://download.pytorch.org/whl/cpu`
index using `[tool.uv.sources]` in `pyproject.toml`.

**Rationale:** Removes 21 NVIDIA CUDA packages from the lockfile (~1.5 GB). The
CPU wheel is sufficient for ConvNeXt-Tiny inference at the required latency budget.
The index configuration is transparent — changing it to CUDA in a GPU deployment
requires only a one-line `pyproject.toml` edit.

---

## ADR-010 — Argon2id for password hashing (pwdlib)

**Context:** fastapi-users requires a compatible password hash backend.

**Decision:** `pwdlib[argon2]` with default Argon2id parameters.

**Rationale:** Argon2id (OWASP recommended) is memory-hard and resistant to GPU-
accelerated cracking. `pwdlib` is the default recommended by the fastapi-users
maintainers, so the hash format is fully compatible with their internal verification.

---

## ADR-011 — Streamlit for the operational dashboard

**Context:** Operators (admin, reviewer, auditor) need a UI to browse batches,
review predictions, manage users, and view the audit log.

**Options considered:**
- React SPA (full control; requires separate build + serve pipeline; overkill for internal tool)
- Gradio (ML-focused; limited for multi-page admin dashboards)
- Streamlit (Python-native; multi-tab; data tables; file uploader; deploys as one script)

**Decision:** Streamlit.

**Rationale:** The entire UI is a single Python file with no build step. The file uploader
widget covers the HTTP-upload use-case. Tabs are role-gated at render time. The
dashboard connects to the same FastAPI API as any other client, so it exercises the
real authentication and authorization paths.
