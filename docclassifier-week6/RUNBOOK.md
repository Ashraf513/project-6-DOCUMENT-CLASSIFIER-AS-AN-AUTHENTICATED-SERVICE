# Runbook — Day-to-Day Operations

## First-Time Setup

```powershell
# 1. Clone the repo
git clone <repo-url>
cd docclassifier-week6

# 2. Create the environment file
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux

# 3. Build and start all services
docker-compose up --build

# 4. Seed the first admin user (in a second terminal)
docker-compose run --rm api python scripts/seed_admin.py

# 5. Open the interactive API docs
#    http://localhost:8000/docs
```

For full step-by-step instructions see [test_locally.md](test_locally.md).

---

## Starting and Stopping

```powershell
# Start all services (foreground — logs visible)
docker-compose up

# Start in the background (detached)
docker-compose up -d

# Stop all services (keeps data volumes)
docker-compose down

# Stop and delete all data (full reset)
docker-compose down -v

# Rebuild images after code changes
docker-compose up --build
```

---

## Viewing Logs

```powershell
# All services
docker-compose logs -f

# One service
docker-compose logs -f api
docker-compose logs -f worker
docker-compose logs -f sftp-ingest

# Last 50 lines
docker-compose logs --tail=50 api
```

---

## Checking Service Health

```powershell
# API health endpoint
curl http://localhost:8000/health

# See which containers are running and their status
docker-compose ps
```

Expected output of `docker-compose ps` when everything is healthy:

```
NAME                STATUS          PORTS
...-api-1           Up (healthy)    0.0.0.0:8000->8000/tcp
...-worker-1        Up              
...-sftp-ingest-1   Up              
...-db-1            Up (healthy)    
...-redis-1         Up (healthy)    
...-minio-1         Up (healthy)    0.0.0.0:9000->9000/tcp
...-sftp-1          Up              0.0.0.0:2222->22/tcp
...-vault-1         Up (healthy)    0.0.0.0:8200->8200/tcp
```

---

## User Management

### Create a new user (admin only)

Use the Swagger UI at `http://localhost:8000/docs` → `POST /users/`, or with curl:

```bash
TOKEN="<your-admin-jwt-token>"

curl -X POST http://localhost:8000/users/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "new@example.com", "password": "Secure1234!", "role": "reviewer"}'
```

### Change a user's role

```bash
USER_ID="<uuid-of-target-user>"

curl -X PATCH http://localhost:8000/users/$USER_ID/role \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "auditor"}'
```

### List all users

```bash
curl http://localhost:8000/users/ \
  -H "Authorization: Bearer $TOKEN"
```

---

## Dropping Test Documents via SFTP

The SFTP server simulates a scanner vendor. Drop TIFF files into it to trigger the ingest pipeline:

```bash
# Using sftp CLI (Mac/Linux)
sftp -P 2222 scanner@localhost
sftp> put mydocument.tiff /upload/

# Using WinSCP or FileZilla (Windows):
# Host: localhost  Port: 2222  User: scanner  Password: scanner
# Upload any .tiff file to the /upload/ directory
```

Within 5–10 seconds, the file will appear in the API as a batch with a prediction.

---

## Accessing MinIO (File Storage)

MinIO web console: `http://localhost:9001`
- Username: `minioadmin`
- Password: `minioadmin`

Files are stored in the `documents` bucket under:
```
batches/{batch_id}/original/{filename}.tiff   ← original scan
batches/{batch_id}/overlay/{filename}.png     ← annotated result
```

---

## Accessing HashiCorp Vault

Vault UI: `http://localhost:8200`
- Method: Token
- Token: `root` (from `.env`)

Secrets path: `secret/docclassifier`

To read secrets via CLI:
```bash
docker-compose exec vault vault kv get -mount=secret docclassifier
```

---

## Database Access

Connect to Postgres with any SQL client (DBeaver, pgAdmin, TablePlus):
```
Host:     localhost
Port:     5432
Database: docclassifier
User:     docclassifier
Password: docclassifier_dev
```

Or use psql inside the container:
```bash
docker-compose exec db psql -U docclassifier -d docclassifier
```

---

## Running Database Migrations

Migrations run automatically in the `migrate` container on every `docker-compose up`.
To run them manually:

```bash
docker-compose run --rm migrate alembic upgrade head

# Check migration history
docker-compose run --rm migrate alembic history

# Roll back one migration
docker-compose run --rm migrate alembic downgrade -1
```

---

## Rebuilding a Single Service

```bash
# Rebuild only the API image (after code changes)
docker-compose up --build api

# Rebuild only the worker
docker-compose up --build worker
```

---

## Troubleshooting

### API keeps restarting

```bash
docker-compose logs api
```

Common causes:
- **Vault not healthy yet** — wait 30 s and run `docker-compose up` again
- **DB migrations not complete** — check `docker-compose logs migrate`
- **`DEV_SKIP_MODEL_CHECK` not set** — add it to `.env` if weights are missing

### "Could not connect to server" in seed script

The database isn't ready yet. Wait for `migrate-1 exited with code 0` in the logs,
then re-run:
```bash
docker-compose run --rm api python scripts/seed_admin.py
```

### Port already in use

Edit `.env` to change the conflicting port:
```
API_PORT=8080
POSTGRES_PORT=5433
```
Then restart: `docker-compose down && docker-compose up`

### Worker not processing jobs

Check that the `worker` container is running:
```bash
docker-compose ps worker
docker-compose logs worker
```

The worker requires the ML model weights (`app/classifier/models/classifier.pt`).
If weights are missing, the worker refuses to start (unless `DEV_SKIP_MODEL_CHECK=1`
is also applied to the worker — currently it is not; inference requires real weights).

### Vault secrets missing after `docker-compose down -v`

The `-v` flag deletes volumes, which wipes Vault's state. On the next `up`, `vault-init`
will re-seed all secrets automatically.

---

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| API + Swagger UI | http://localhost:8000/docs | admin@example.com / Admin1234! |
| MinIO web console | http://localhost:9001 | minioadmin / minioadmin |
| HashiCorp Vault UI | http://localhost:8200 | Token: root |
| SFTP | localhost:2222 | scanner / scanner |
| Postgres | localhost:5432 | docclassifier / docclassifier_dev |
| Redis | localhost:6379 | no auth |
