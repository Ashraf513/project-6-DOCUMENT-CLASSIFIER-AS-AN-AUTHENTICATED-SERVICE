# Runbook — Document Classifier Service

Day-to-day operational procedures for the Document Classifier microservice.

---

## Health checks

```powershell
# Overall stack status
docker compose ps

# API health endpoint
curl.exe -s http://localhost:8000/health

# Redis connectivity
docker compose exec redis redis-cli ping    # → PONG

# Postgres connectivity
docker compose exec db pg_isready -U docclassifier -d docclassifier

# RQ queue depth (0 = idle, >0 = jobs waiting)
docker compose exec redis redis-cli llen rq:queue:default

# Failed jobs
docker compose exec redis redis-cli llen rq:queue:failed
```

---

## Starting and stopping

```powershell
# Start full stack (first time — builds images)
docker compose up --build -d

# Start without rebuild (subsequent times)
docker compose up -d

# Start only core services (no dashboard / pgAdmin)
docker compose up -d api worker sftp-ingest

# Stop everything (keeps volumes — data preserved)
docker compose down

# Stop and wipe all data (volumes deleted)
docker compose down --volumes

# Restart a single service without rebuilding
docker compose restart api
docker compose restart worker
```

---

## Seeding the first admin

Run once after the stack is up for the first time:

```powershell
docker compose run --rm --entrypoint python api scripts/seed_admin.py
```

Default credentials: `admin@example.com` / `Admin1234!`

Override with environment variables:
```powershell
$env:SEED_ADMIN_EMAIL    = "ops@company.com"
$env:SEED_ADMIN_PASSWORD = "SecurePass1!"
docker compose run --rm --entrypoint python api scripts/seed_admin.py
```

The script is idempotent — it skips if an admin already exists.

---

## Adding a new user

Via the API (admin token required):

```powershell
curl.exe -s -X POST http://localhost:8000/users/ `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"email":"reviewer@co.com","password":"Temp1234!","role":"reviewer"}' `
  | ConvertFrom-Json
```

Via the Streamlit dashboard: **Users** tab → **Invite new user** section.

---

## Changing a user's role

```powershell
# Get the user's ID first
$users = curl.exe -s http://localhost:8000/users/ `
  -H "Authorization: Bearer $token" | ConvertFrom-Json

$uid = ($users | Where-Object { $_.email -eq "user@co.com" }).id

# Change role
curl.exe -s -X PATCH "http://localhost:8000/users/$uid/role" `
  -H "Authorization: Bearer $token" `
  -H "Content-Type: application/json" `
  -d '{"role":"auditor"}' | ConvertFrom-Json
```

---

## Deleting a user

```powershell
curl.exe -s -X DELETE "http://localhost:8000/users/$uid" `
  -H "Authorization: Bearer $token"
# Returns 204 No Content on success
# Audit log entries for this user are preserved (actor_id set to NULL)
```

Safeguards enforced by the service layer:
- Cannot delete your own account
- Cannot delete the last admin

---

## Monitoring predictions

```powershell
# Recent predictions (last 10)
curl.exe -s "http://localhost:8000/predictions/recent?limit=10" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json | Format-Table

# Predictions for a specific batch
curl.exe -s "http://localhost:8000/predictions/batch/$batchId" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json | Format-Table
```

---

## Handling a stuck batch

A batch can get stuck in `processing` if the worker job fails after `mark_processing`
was committed but before `mark_done` ran.

**Diagnose:**

```powershell
# See which batches are stuck
docker compose exec db psql -U docclassifier -d docclassifier -c "
SELECT id, status, file_count, created_at
FROM batches
WHERE status = 'processing'
ORDER BY created_at;"

# Check worker logs
docker compose logs worker --tail=50

# Check the RQ failed queue
docker compose exec redis redis-cli llen rq:queue:failed
docker compose exec redis redis-cli lrange rq:queue:failed 0 -1
```

**Fix:**

```powershell
# Mark stuck batches as failed so they no longer show as in-progress
docker compose exec db psql -U docclassifier -d docclassifier -c "
UPDATE batches SET status = 'failed'
WHERE status = 'processing'
  AND updated_at < NOW() - INTERVAL '10 minutes';"
```

To reprocess a failed batch, re-drop the original TIFF files via SFTP or HTTP upload.
The SFTP watcher skips files already present in MinIO (idempotency via `blob.exists()`),
so use a different filename or clear MinIO first.

---

## Clearing the RQ failed queue

```powershell
# See failed job exception info (replace <job_id> from lrange above)
docker compose exec redis redis-cli hget rq:job:<job_id> exc_info

# Clear all failed jobs
docker compose exec redis redis-cli del rq:queue:failed
```

---

## Adding a new Casbin permission

The Casbin policy table is seeded once at first boot. To add a new rule to a running
stack:

```powershell
docker compose exec db psql -U docclassifier -d docclassifier -c "
INSERT INTO casbin_rule (ptype, v0, v1, v2)
VALUES ('p', 'admin', '/new/endpoint', 'GET')
ON CONFLICT DO NOTHING;"

# Reload the enforcer
docker compose restart api
```

Also add the rule to `casbin/policy.csv` so it is seeded on the next fresh deployment.

---

## Viewing the audit log

```powershell
# Last 50 entries via API
curl.exe -s "http://localhost:8000/audit/?limit=50" `
  -H "Authorization: Bearer $token" | ConvertFrom-Json | Format-Table

# Direct DB query (useful for large datasets or date filtering)
docker compose exec db psql -U docclassifier -d docclassifier -c "
SELECT timestamp, action, actor_id, target, details
FROM audit_logs
ORDER BY timestamp DESC
LIMIT 50;"
```

---

## Rebuilding after code changes

```powershell
# Rebuild one service (uses Docker layer cache — fast for code-only changes)
docker compose up --build -d api

# Rebuild worker after changing inference_worker.py
docker compose up --build -d worker

# Rebuild all (pyproject.toml or uv.lock changed — slow first run)
docker compose up --build -d
```

---

## Updating secrets in Vault

```powershell
# Connect to the Vault container
docker compose exec vault sh

# Inside vault shell
vault kv patch secret/docclassifier JWT_SECRET="new-secret-here"

# Restart the API to pick up the new secret
docker compose restart api
```

---

## pgAdmin — database browser

1. Open http://localhost:5050
2. Login: `admin@admin.com` / `admin` (override in `.env`)
3. Register server: Host = `db`, Port = `5432`, Database = `docclassifier`, User/Pass = `docclassifier` / `docclassifier_dev`

---

## MinIO console — blob browser

1. Open http://localhost:9001
2. Login: `minioadmin` / `minioadmin`
3. Navigate to bucket `documents`

Key prefixes:
- `batches/{batch_id}/original/` — raw TIFF files
- `batches/{batch_id}/overlay/` — annotated PNG results
- `quarantine/{batch_id}/` — rejected files (wrong extension, zero-byte, oversized)

---

## Log locations

All services log to stdout and are accessible via:

```powershell
docker compose logs <service> --tail=100 --follow
```

| Service | Key log events |
|---|---|
| `api` | HTTP requests, Casbin decisions, cache hits |
| `worker` | `job_started`, `inference_done`, `job_completed`, exceptions |
| `sftp-ingest` | `Detected N new file(s)`, `Enqueued classify job`, SFTP errors |
| `migrate` | Alembic migration output |
| `vault-init` | Secret seeding confirmation |
