# Architecture Decision Records

Each entry records a technology choice, why it was made, and what the alternatives were.

---

## ADR-001: FastAPI over Flask or Django

**Decision:** Use FastAPI as the web framework.

**Why:**
- Native async support — essential for SQLAlchemy 2.x async and non-blocking Redis calls.
- Automatic OpenAPI/Swagger UI generation — no separate documentation effort.
- Pydantic v2 integration — request/response validation is built-in, not bolted on.
- Dependency injection system — clean way to inject DB sessions, current user, and services per request.

**Alternatives considered:**
- Flask: no built-in async, no validation, no auto-docs.
- Django REST Framework: synchronous by default, heavy ORM doesn't compose with async SQLAlchemy.

---

## ADR-002: fastapi-users over Custom Auth

**Decision:** Use `fastapi-users` (v15+) for JWT authentication and user management.

**Why:**
- Password hashing (Argon2id), JWT creation/verification, and session management are security-sensitive.
  Getting these wrong is a critical vulnerability. Using a well-maintained library reduces that risk.
- fastapi-users integrates directly with async SQLAlchemy and FastAPI's dependency injection.
- It handles token refresh, password reset flows, and email verification — features we don't have to build.

**Trade-off:** the library adds some complexity to the `UserManager` setup. The `@property` pattern
for secrets (instead of class attributes) is required because secrets are fetched from Vault lazily,
not at import time.

---

## ADR-003: Casbin RBAC over Custom Permission Checks

**Decision:** Use PyCasbin with the SQLAlchemy adapter for role-based access control.

**Why:**
- The brief requires three distinct roles (admin, reviewer, auditor) with different resource permissions.
  A policy table is more maintainable than scattered `if user.role == "admin"` checks in routes.
- Casbin stores policies in the database — they can be inspected and audited.
- The `casbin-sqlalchemy-adapter` seeds rules from `casbin/policy.csv` on first boot and persists
  them in the DB for subsequent starts.

**Trade-off:** Casbin's sync SQLAlchemy adapter requires an `asyncio.to_thread()` wrapper at
startup and a `psycopg2` sync connection URL alongside the `asyncpg` async URL.
This is a one-time cost at startup and does not affect request performance.

---

## ADR-004: RQ (Redis Queue) over Celery

**Decision:** Use RQ for background job queuing.

**Why:**
- RQ requires only Redis — no separate broker (RabbitMQ, etc.) needed. Redis is already used for caching.
- RQ's API is minimal: `queue.enqueue(fn, *args)` to submit, `rq worker` to consume. No config files.
- For this project's scale (classification jobs one at a time), RQ's simplicity is appropriate.

**Alternatives considered:**
- Celery: more features (retries, periodic tasks, routing) but requires a broker, significant config,
  and adds ~30 MB to the dependency footprint.
- Python `asyncio` tasks: not durable — in-flight tasks are lost on restart. RQ persists jobs in Redis.

---

## ADR-005: MinIO over Local Filesystem

**Decision:** Use MinIO for blob (file) storage.

**Why:**
- Documents must survive container restarts. A local filesystem inside a container is ephemeral.
- MinIO is S3-compatible — the same client code works against AWS S3 in production with only
  an endpoint change.
- Presigned URLs allow API users to download files directly from MinIO without routing through
  the API server (reducing bandwidth and latency).
- MinIO separates the concern of file storage from the application's compute containers.

---

## ADR-006: HashiCorp Vault over .env Files

**Decision:** Store all application secrets in Vault; `.env` holds only the Vault token and port numbers.

**Why:**
- `.env` files are frequently committed to git by accident. The consequences of leaking a JWT
  signing key or database password are severe.
- Vault logs every secret read — you can audit who accessed what and when.
- Vault can rotate secrets without redeploying; the app just fetches the new value on next start.
- The Vault dev mode container is easy to run locally; the same client code works against
  a production Vault cluster.

**Trade-off:** adds one more service to the local stack and requires the `hvac` client.
If Vault is unreachable at startup, the API refuses to boot — this is intentional (fail-fast).

---

## ADR-007: ConvNeXt Tiny/Small over ResNet or ViT

**Decision:** Use ConvNeXt Tiny (or Small) as the image classification backbone.

**Why:**
- ConvNeXt achieves better accuracy per parameter than ResNet on document layout tasks.
- ConvNeXt runs efficiently on CPU — p95 inference < 1.0 s on a laptop (the brief's requirement).
  Vision Transformers (ViT) are significantly slower on CPU due to attention computation.
- `torchvision` ships ConvNeXt with pre-trained ImageNet weights — no custom weight download needed.
- Fine-tuning only the classification head first (linear probe) then partially unfreezing converges
  in 3–5 epochs on Colab T4.

**Target:** ≥ 85% top-1 accuracy on the 40k RVL-CDIP test split.

---

## ADR-008: uv over pip or Poetry

**Decision:** Use `uv` as the Python package manager and `pyproject.toml` + `uv.lock` for dependency management.

**Why:**
- `uv` is 10–100× faster than pip for resolving and installing dependencies — critical for Docker build times.
- `uv.lock` is a deterministic lockfile — identical installs across machines and CI.
- `UV_LINK_MODE=copy` is required in multi-stage Docker builds because hardlinks/symlinks don't
  survive `COPY --from` across build stages. Without this, the venv in the final image would be broken.
- `uv venv` + `uv sync --frozen --no-dev` produces a lean venv with only production dependencies.

---

## ADR-009: Single Dockerfile with Multi-Stage Builds

**Decision:** One `Dockerfile` with 8 stages and 4 named final targets.

**Why:**
- All four services share: the same base image, the same lockfile, and the same `app/` source tree.
  A single Dockerfile means `deps-api` is built once and reused by `api`, `sftp-ingest`, and `migrate`.
- Multiple Dockerfiles (one per service) would install dependencies 4× per build — 4× slower,
  no shared layer cache.
- `docker-compose.yml` references the 4 final targets via `build.target` — clean separation of concerns.

**Stage breakdown:**
- `uv` — donor stage (provides the uv binary)
- `system-base` — OS runtime libs, no build tools
- `builder-base` — adds gcc, libpq-dev, uv for compiling C extensions
- `deps-api` — installs all Python deps except torch
- `deps-worker` — inherits deps-api, adds CPU-only torch
- `api`, `worker`, `sftp-ingest`, `migrate` — the four final images

---

## ADR-010: Removing /auth/register

**Decision:** Remove the public `/auth/register` endpoint.

**Why:**
- An open registration endpoint allowed any anonymous user to create accounts with any role —
  a critical privilege escalation risk.
- The brief specifies that users are invited by admins, not self-registered.
- Accounts are created only via `POST /users/` which requires an `admin` JWT.
- The first admin is seeded via `scripts/seed_admin.py` run against the running database.

---

## ADR-011: Casbin Policy Stored in DB (Not File)

**Decision:** Load Casbin policies from the database via `casbin-sqlalchemy-adapter`, seeding
from `casbin/policy.csv` only on first boot when the DB table is empty.

**Why:**
- File-based policies require a container restart to update. DB-based policies can be changed
  at runtime via Vault or a management API.
- The DB is the authoritative state — the CSV file is only the initial seed.
- The SQLAlchemy adapter creates the `casbin_rule` table automatically via Alembic integration.

**Trade-off:** the adapter is synchronous, requiring `asyncio.to_thread()` at startup and a
separate `psycopg2` sync connection. This is a one-time startup cost.
