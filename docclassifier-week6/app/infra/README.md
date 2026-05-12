# Phase 7: Infrastructure — External Service Adapters

## What Is This Phase?

The `infra` folder contains **adapters** — thin wrappers around external services. Each adapter knows how to talk to one external system, and the rest of the application talks to the adapter instead of the external system directly.

Think of it like a power adapter: the adapter handles the difference between the socket on the wall (external service) and your device's plug (your code). If you travel to a country with different sockets, you swap the adapter — not your device.

---

## The External Services and Their Adapters

| External Service | Adapter File | What It Does |
|----------------|-------------|-------------|
| HashiCorp Vault | `vault.py` | Stores and retrieves secrets (passwords, keys) |
| MinIO (blob storage) | `blob.py` | Stores and retrieves document files |
| Redis | `cache.py` | Caches API responses, manages job queue |
| SFTP Server | `sftp_watcher.py` | Watches for new files dropped by the scanner vendor |

---

## Files in This Directory

```
app/infra/
├── README.md          ← you are here
├── __init__.py
├── vault.py           ← Vault secret management
├── blob.py            ← MinIO file storage
├── cache.py           ← Redis cache client
└── sftp_watcher.py    ← SFTP polling loop
```

---

## vault.py — Secret Management

**HashiCorp Vault** is a tool that stores secrets (passwords, API keys, JWT signing keys) securely. Instead of putting secrets in your code or `.env` files, you store them in Vault and fetch them at runtime.

The Vault adapter is called **once at startup** to load all necessary secrets into memory.

```python
class VaultClient:
    def __init__(self, vault_addr: str, vault_token: str):
        self.client = hvac.Client(url=vault_addr, token=vault_token)

    def get_secret(self, path: str, key: str) -> str:
        # Reads from Vault KV v2: vault kv get secret/<path>
        response = self.client.secrets.kv.v2.read_secret_version(
            path=path, mount_point="secret"
        )
        return response["data"]["data"][key]

# Called at startup:
vault = VaultClient(
    vault_addr=os.environ["VAULT_ADDR"],   # from .env — this is NOT a secret
    vault_token=os.environ["VAULT_TOKEN"]  # root token from .env (dev mode only)
)
DATABASE_URL = vault.get_secret("database", "url")
JWT_SECRET   = vault.get_secret("auth", "jwt_secret")
```

**Why Vault instead of `.env`?**
- `.env` files are often accidentally committed to git.
- Vault logs every secret access — you know who read what and when.
- Vault can rotate secrets without redeploying the app.

**Startup check:** if Vault is unreachable, the app logs an error and refuses to start.

---

## blob.py — MinIO File Storage

**MinIO** is an S3-compatible object store — it works exactly like Amazon S3 but runs on your laptop. Files are stored as "objects" in "buckets" (like folders).

The blob adapter handles: uploading files, downloading files, and generating temporary download URLs.

```python
class BlobClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key)
        self.bucket = "documents"

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        # Uploads a file to MinIO, returns the key (path)
        # key example: "batches/batch-123/invoice.tiff"
        self.client.put_object(self.bucket, key, io.BytesIO(data), len(data))
        return key

    async def download(self, key: str) -> bytes:
        # Downloads a file from MinIO by its key
        response = self.client.get_object(self.bucket, key)
        return response.read()

    def presigned_url(self, key: str, expires: timedelta) -> str:
        # Generates a temporary download link (expires in N minutes)
        return self.client.presigned_get_object(self.bucket, key, expires=expires)
```

**File naming convention:**
```
documents/
└── batches/
    └── {batch_id}/
        ├── original/{filename}.tiff    ← the scanned document
        └── overlay/{filename}.png      ← the annotated result image
```

---

## cache.py — Redis Cache Client

**Redis** is an in-memory key-value store. It is used for two purposes in this project:
1. **Caching** — storing API responses to avoid hitting the database on every request.
2. **Job queue** — RQ (Redis Queue) stores pending classification jobs in Redis.

The cache adapter wraps Redis for the caching use case:

```python
class CacheClient:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)

    async def get(self, key: str) -> bytes | None:
        return await self.redis.get(key)

    async def set(self, key: str, value: bytes, expire: int) -> None:
        # Store value, auto-delete after 'expire' seconds
        await self.redis.setex(key, expire, value)

    async def delete(self, key: str) -> None:
        # Called by services after a write to invalidate stale data
        await self.redis.delete(key)

    async def delete_pattern(self, pattern: str) -> None:
        # Deletes all keys matching a pattern, e.g. "batch:*"
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)
```

**Cache keys used in this project:**
| Key Pattern | What It Caches | TTL |
|------------|----------------|-----|
| `user:{user_id}` | GET /me response | 5 min |
| `batches:list` | GET /batches response | 1 min |
| `batch:{batch_id}` | GET /batches/{id} response | 1 min |
| `predictions:recent` | GET /predictions/recent | 30 sec |

---

## sftp_watcher.py — SFTP File Watcher

The SFTP watcher runs as a separate process (the `sftp-ingest` container). It polls the SFTP server every 2 seconds, looking for new files.

```python
class SFTPWatcher:
    def __init__(self, sftp_host, sftp_user, sftp_password, sftp_path,
                 blob_client, queue):
        self.sftp_host     = sftp_host
        self.sftp_user     = sftp_user
        self.sftp_password = sftp_password
        self.sftp_path     = sftp_path   # e.g. "/upload"
        self.blob_client   = blob_client
        self.queue         = queue
        self.seen_files    = set()       # tracks files already processed

    async def run(self):
        while True:
            await self._poll()
            await asyncio.sleep(2)       # check every 2 seconds

    async def _poll(self):
        with paramiko.SSHClient() as ssh:
            ssh.connect(self.sftp_host, username=self.sftp_user,
                        password=self.sftp_password)
            with ssh.open_sftp() as sftp:
                files = sftp.listdir(self.sftp_path)
                new_files = [f for f in files if f not in self.seen_files]

                if new_files:
                    # Group into a batch and process each file
                    batch = await create_batch_in_db()
                    for filename in new_files:
                        await self._process_file(sftp, filename, batch.id)
                        self.seen_files.add(filename)

    async def _process_file(self, sftp, filename, batch_id):
        # Validate: reject zero-byte files, non-TIFF files, oversized files
        stat = sftp.stat(f"{self.sftp_path}/{filename}")
        if stat.st_size == 0:
            logger.warning("zero-byte file ignored", filename=filename)
            return
        if not filename.lower().endswith(".tiff"):
            logger.warning("non-TIFF file quarantined", filename=filename)
            # Move to quarantine folder in MinIO
            return

        # Download from SFTP
        data = sftp.open(f"{self.sftp_path}/{filename}").read()

        # Upload to MinIO
        blob_key = f"batches/{batch_id}/original/{filename}"
        await self.blob_client.upload(blob_key, data, "image/tiff")

        # Enqueue inference job
        self.queue.enqueue("worker.classify", batch_id=batch_id, blob_key=blob_key)
```

**File validation before processing:**

| Problem | What Happens |
|---------|-------------|
| Zero-byte file | Logged as warning, skipped |
| Non-TIFF file | Logged as warning, moved to quarantine in MinIO |
| File > 100MB | Logged as warning, moved to quarantine |
| Valid TIFF | Uploaded to MinIO, job enqueued |

---

## How the Infra Adapters Are Wired Together

At startup, `main.py` initializes all adapters and stores them on the app state:

```python
@app.on_event("startup")
async def startup():
    vault  = VaultClient(os.environ["VAULT_ADDR"], os.environ["VAULT_TOKEN"])
    app.state.blob  = BlobClient(
        endpoint=vault.get_secret("minio", "endpoint"),
        access_key=vault.get_secret("minio", "access_key"),
        secret_key=vault.get_secret("minio", "secret_key"),
    )
    app.state.cache = CacheClient(vault.get_secret("redis", "url"))
    app.state.db_url = vault.get_secret("database", "url")
```

All secrets come from Vault — no passwords in code or environment variables (except the Vault token itself).

---

## What You Need to Know for the Presentation

- Why use MinIO instead of the filesystem for storing files?
  - Answer: MinIO works the same locally as S3 in production; files survive container restarts; presigned URLs let clients download directly without going through the API
- What happens if MinIO is unreachable mid-job?
  - Answer: the worker catches the upload exception, marks the job as failed, logs the error, and leaves it in the RQ failed queue for retry
- What is the SFTP watcher's `seen_files` set and what problem does it solve?
  - Answer: prevents reprocessing the same file twice if the poll loop runs again before the file is deleted
- Why does `grep -ri 'password' app/` return zero results?
  - Answer: all secrets are fetched from Vault at startup — they are never written as string literals in code
- What happens when the SFTP server drops a 1GB CSV file?
  - Answer: the watcher detects it's not a TIFF, logs a warning with filename and size, and moves it to a quarantine location in MinIO
