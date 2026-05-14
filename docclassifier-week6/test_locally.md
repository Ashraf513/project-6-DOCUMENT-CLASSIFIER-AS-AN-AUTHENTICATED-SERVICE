# Testing the Document Classifier Locally

## What works right now vs what doesn't

| Feature | Status | Why |
|---|---|---|
| All infrastructure (Postgres, Redis, MinIO, Vault) | ✅ Works | Pre-built images |
| API: login, users, batches list, audit logs | ✅ Works | Code complete |
| Health check at `/health` | ✅ Works | |
| Swagger UI / interactive docs | ✅ Works | |
| Submitting a batch (POST /batches/) | ⚠️ Queues but no result | Worker is empty stub |
| Inference / overlay image | ❌ Not yet | Needs Colab-trained weights |
| SFTP auto-ingest | ❌ Not yet | Worker is empty stub |

---

## Step 0 — Prerequisites (install once)

1. **Docker Desktop** — download from https://www.docker.com/products/docker-desktop and install it.
   On Windows you need WSL 2 enabled — the installer will tell you if it isn't.
2. After installing, open Docker Desktop and wait until the whale icon in the system tray turns **green** (engine running).
3. No Python needed on your machine — everything runs inside containers.

---

## Step 1 — Open a terminal in the project folder

Open **PowerShell** or **Windows Terminal**, then navigate here:

```powershell
cd "e:\AIE-SE Factory\project 6\project-6-DOCUMENT-CLASSIFIER-AS-AN-AUTHENTICATED-SERVICE-dev\docclassifier-week6"
```

---

## Step 2 — Create your `.env` file

```powershell
copy .env.example .env
```

The `.env` file includes `DEV_SKIP_MODEL_CHECK=1` so the API starts without trained model weights.
Do **not** commit `.env` — it is already in `.gitignore`.

---

## Step 3 — Build and start the stack

```powershell
docker-compose up --build
```

**First run takes 5–15 minutes** — Docker downloads base images and installs Python packages.
Subsequent runs take under 30 seconds because layers are cached.

Watch the logs. You are waiting for this line from the `api` service:

```
api-1  | Application startup complete.
```

Early red errors are normal — some services wait for others to become healthy before starting.

---

## Step 4 — Seed the first admin user

Open a **second terminal**, navigate to the same folder, and run:

```powershell
docker-compose run --rm api python scripts/seed_admin.py
```

Expected output:

```
[seed-admin] Admin created successfully.
             Email   : admin@example.com
             Password: Admin1234!
             → Login at http://localhost:8000/docs
```

Safe to run multiple times — if an admin already exists it skips silently.

---

## Step 5 — Open Swagger UI

```
http://localhost:8000/docs
```

---

## Step 6 — Log in

1. Click **`POST /auth/jwt/login`** → **Try it out** → **Execute**
2. Fill in:
   - `username`: `admin@example.com`
   - `password`: `Admin1234!`
3. Copy the `access_token` from the response body
4. Click the **Authorize** button (padlock icon, top right)
5. Paste the token into the `bearerAuth` field → **Authorize**

All endpoints are now unlocked for your admin session.

---

## Step 7 — Try the endpoints

**GET /health** — confirms the API is alive:
```json
{"status": "healthy", "service": "document-classifier-api"}
```

**GET /users/** — list all users (admin only):
```json
[{"id": "...", "email": "admin@example.com", "role": "admin"}]
```

**POST /users/** — create a reviewer or auditor account:
```json
{
  "email": "reviewer@example.com",
  "password": "Review1234!",
  "role": "reviewer"
}
```

**GET /batches/** — list document batches (empty at first):
```json
[]
```

**GET /audit/** — audit trail of all admin actions:
```json
[{"action": "user_create", "target": "user:...", ...}]
```

---

## Stopping and restarting

```powershell
# Stop all containers (keeps database data intact)
Ctrl+C

# Start again later — no rebuild needed, much faster
docker-compose up

# Full reset: wipe all data and start fresh
docker-compose down -v
docker-compose up --build
```

---

## Service URLs

| Service | URL | Credentials |
|---|---|---|
| API + Swagger UI | http://localhost:8000/docs | admin@example.com / Admin1234! |
| MinIO web console | http://localhost:9001 | minioadmin / minioadmin |
| HashiCorp Vault UI | http://localhost:8200 | Token: `root` |
| SFTP | localhost:2222 | scanner / scanner |
| Postgres | localhost:5432 | docclassifier / docclassifier_dev |

---

## Troubleshooting

**`api` keeps restarting after startup**
Check logs with `docker-compose logs api`. Most likely Vault is not yet healthy — wait 30 s and try `docker-compose up` again.

**`seed_admin.py` says "could not connect to server"**
The database is not ready yet. Wait for `migrate` to finish (look for `migrate-1 exited with code 0` in the logs), then re-run the seed command.

**Port already in use**
Another application is using port 8000, 5432, 6379, etc. Edit `.env` to change the conflicting port (e.g. `API_PORT=8080`) and re-run `docker-compose up`.

**Docker Desktop not starting on Windows**
Make sure WSL 2 is enabled: open PowerShell as Administrator and run `wsl --install`, then restart your machine.
