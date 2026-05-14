# Collaboration Guide

## Project Structure at a Glance

```
docclassifier-week6/
├── app/
│   ├── api/          Phase 6 — HTTP layer (routers, deps, main)
│   ├── classifier/   Phase 1 — ML model loading and inference
│   ├── db/           Phase 2 — SQLAlchemy ORM models and session
│   ├── domain/       Phase 3 — Pydantic domain models
│   ├── infra/        Phase 7 — External service adapters (Vault, MinIO, Redis, SFTP)
│   ├── repositories/ Phase 4 — Database queries
│   ├── services/     Phase 5 — Business logic
│   └── workers/      Phase 8 — Background job processes
├── alembic/          Database migration scripts
├── casbin/           RBAC policy model and seed CSV
├── scripts/          Utility scripts (seed_admin.py)
├── Dockerfile        Multi-stage build (4 final targets)
├── docker-compose.yml Full local stack (11 services)
└── pyproject.toml    Python dependencies (uv)
```

---

## Layer Ownership

Each layer has a clear owner and a strict contract with adjacent layers.

| Layer | Files | Accepts | Returns | Never Does |
|-------|-------|---------|---------|-----------|
| Routers | `app/api/routers/*.py` | HTTP Request | HTTP Response | SQL, business logic |
| Services | `app/services/*.py` | Domain models | Domain models | HTTP errors, SQL |
| Repositories | `app/repositories/*.py` | Domain models | Domain models | HTTP errors, cache ops |
| DB models | `app/db/models.py` | — | — | Imported only by repos |
| Domain models | `app/domain/*.py` | — | — | SQL or HTTP logic |
| Infra adapters | `app/infra/*.py` | — | — | Business logic |

**The most important rule:** HTTP exceptions (`HTTPException`) are raised only in routers.
Services and repositories raise plain Python exceptions (`ValueError`, `PermissionError`, `NotFound`).

---

## Adding a New Feature — Checklist

When adding a new capability (e.g. "export batch as CSV"):

1. **Domain model** — add a new Pydantic class in `app/domain/` if a new data shape is needed.
2. **DB migration** — if a new column or table is needed:
   ```bash
   # Edit app/db/models.py first, then generate the migration
   docker-compose run --rm migrate alembic revision --autogenerate -m "add export_log table"
   ```
3. **Repository** — add the query method in `app/repositories/`.
4. **Service** — add the business logic in `app/services/`. Wrap DB writes in `async with self.db.begin()`.
5. **Router** — add the HTTP endpoint in `app/api/routers/`. Map service exceptions to HTTP status codes.
6. **Casbin policy** — if the new endpoint needs permission control, add a line to `casbin/policy.csv`.
7. **Tests** — add a test in the appropriate test file.
8. **README** — update the relevant `app/*/README.md` if the interface changed.

---

## Git Workflow

```
main
 └── feature/your-feature-name   ← work here
      └── pull request → main
```

Branch naming:
- `feature/` — new functionality
- `fix/` — bug fix
- `infra/` — Docker, CI, dependencies

Commit message format:
```
type: short description (under 72 chars)

Optional body explaining WHY, not what.
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `infra`

Example:
```
feat: add CSV export endpoint for completed batches

Reviewers requested a way to download results without using the API.
Endpoint: GET /batches/{id}/export  (admin + reviewer only)
```

---

## Code Review Standards

**Before opening a PR:**
- [ ] `docker-compose up --build` runs without errors
- [ ] `GET /health` returns 200
- [ ] New endpoint appears in Swagger UI at `http://localhost:8000/docs`
- [ ] No `password`, `secret`, or credential string literals in code
  (`grep -ri "password" app/` → zero hits outside of Vault/hashing code)
- [ ] All new endpoints have Casbin policy entries (if applicable)

**Review checklist:**
- [ ] Router raises `HTTPException`, service raises domain exceptions — not swapped
- [ ] Service owns transaction boundaries (`async with self.db.begin()`)
- [ ] Cache is invalidated in the service, not the router or repository
- [ ] Repositories return domain models, not ORM objects
- [ ] No hardcoded secrets or connection strings

---

## Running Tests

```bash
# Unit and integration tests
docker-compose run --rm api pytest

# Specific test file
docker-compose run --rm api pytest test_api_integration.py -v

# With coverage
docker-compose run --rm api pytest --cov=app --cov-report=term-missing
```

Tests that need a live DB (`test_services_integration.py`, `test_api_integration.py`) require
the `db` and `migrate` services to be running first:

```bash
docker-compose up -d db redis vault vault-init migrate
# wait for migrate to finish, then:
docker-compose run --rm api pytest test_api_integration.py
```

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `VAULT_TOKEN` | `root` | Vault dev mode root token |
| `API_PORT` | `8000` | Host port for the API |
| `POSTGRES_PORT` | `5432` | Host port for Postgres |
| `REDIS_PORT` | `6379` | Host port for Redis |
| `MINIO_PORT` | `9000` | Host port for MinIO API |
| `MINIO_CONSOLE_PORT` | `9001` | Host port for MinIO UI |
| `SFTP_PORT` | `2222` | Host port for SFTP |
| `VAULT_PORT` | `8200` | Host port for Vault |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `JWT_LIFETIME_SECONDS` | `86400` | Token lifetime (seconds) |
| `DEV_SKIP_MODEL_CHECK` | `0` | Set to `1` to skip weight integrity check locally |

All variables go in `.env` (copied from `.env.example`). Never commit `.env`.
