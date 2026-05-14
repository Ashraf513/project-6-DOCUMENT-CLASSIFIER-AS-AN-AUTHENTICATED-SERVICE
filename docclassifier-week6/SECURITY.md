# Security Model

## Threat Model Summary

| Threat | Mitigation |
|--------|-----------|
| Stolen credentials | Argon2id password hashing (not reversible) |
| Token theft | Short JWT lifetime (24 h default), signed with Vault-managed secret |
| Horizontal privilege escalation | Casbin RBAC enforced on every request |
| Secrets in code | All secrets in Vault — zero occurrences of credentials as string literals |
| Secrets in `.env` | `.env` holds only the Vault root token and ports; `.gitignore` excludes it |
| Brute-force login | Rate limiter: 5 attempts / 60 s / IP address |
| Open registration | `/auth/register` endpoint removed — users created only by admins via `POST /users/` |
| Last admin lockout | Service layer blocks demotion of the last admin |
| Container privilege escalation | All application containers run as non-root UID 1001 |
| Wrong ML model loaded | SHA-256 integrity check at startup — mismatch aborts boot |
| CORS misconfiguration | Explicit origin allowlist via `CORS_ORIGINS` env var; wildcard `*` with credentials is rejected by spec |

---

## Authentication

Authentication uses **JWT (JSON Web Token)** via fastapi-users 15+.

```
Login flow:
  client POST /auth/jwt/login  (form: username, password)
  → fastapi-users looks up user by email
  → verifies password against Argon2id hash stored in DB
  → creates JWT signed with JWT_SECRET (fetched from Vault)
  → returns {"access_token": "...", "token_type": "bearer"}

Subsequent requests:
  client sends: Authorization: Bearer <token>
  → fastapi-users decodes and verifies the JWT signature
  → loads the user from DB
  → injects as `current_user` dependency into route handlers
```

**JWT secret rotation:** change `JWT_SECRET` in Vault and restart the API containers.
All existing tokens will immediately become invalid (they use the old signature).

**JWT lifetime:** controlled by `JWT_LIFETIME_SECONDS` env var (default: 86400 = 24 h).
Set to a shorter value (e.g. 3600) for higher-security environments.

---

## Authorization (Casbin RBAC)

Every API route is protected by **Casbin** — a policy-based permission library.

The policy is stored in the database (via the SQLAlchemy adapter) and seeded from
`casbin/policy.csv` on first boot.

```
casbin/model.conf  — defines the rule syntax: (subject, object, action)
casbin/policy.csv  — defines which roles can do what

Example policy lines:
  p, admin,    /users,          GET     ← admins can list users
  p, admin,    /users,          POST    ← admins can create users
  p, admin,    /audit,          GET     ← admins can read audit log
  p, reviewer, /batches/detail, GET     ← reviewers can view batches
  p, reviewer, /predictions,    PATCH   ← reviewers can relabel
  p, auditor,  /batches/detail, GET     ← auditors can view (read-only)
  p, auditor,  /audit,          GET     ← auditors can read audit log
```

The enforcer is loaded once at startup and stored on `app.state.enforcer`.
Every route that needs permission checks calls:
```python
enforcer.enforce(actor.role.value, "/resource", "METHOD")
```

---

## Password Storage

Passwords are hashed with **Argon2id** via `pwdlib` (the same library fastapi-users uses internally).

- Argon2id is the winner of the Password Hashing Competition (2015) and is the current OWASP recommendation.
- The hash includes a random salt — two users with the same password get different hashes.
- Plain-text passwords are held in memory only long enough to hash them (one function call in the service layer).
- `grep -ri "password" app/` returns zero string-literal matches outside of the Vault-reading and hashing code.

---

## Secret Management (HashiCorp Vault)

All application secrets live in Vault KV v2 at `secret/docclassifier`.

```
Vault path: secret/docclassifier
Keys:
  JWT_SECRET        — 64-char base64 random, generated at first boot by vault-init
  MINIO_ACCESS_KEY  — MinIO root user
  MINIO_SECRET_KEY  — MinIO root password
  SFTP_USER         — SFTP scanner account username
  SFTP_PASSWORD     — SFTP scanner account password
```

The application fetches secrets at startup via `app/infra/vault.py` using the `hvac` client.
**If Vault is unreachable at startup, the API refuses to boot.**

What is NOT in Vault:
- `DATABASE_URL` — operational config (not a credential), passed via environment
- `VAULT_TOKEN` — the bootstrap credential, must be in `.env` to reach Vault
- Port numbers — not secrets

What is NOT in `.env`:
- Anything else — `.env` is intentionally minimal

---

## Rate Limiting

Login endpoint (`POST /auth/jwt/login`) is rate-limited to **5 attempts per 60 seconds per IP**.
Exceeding the limit returns HTTP 429. The counter resets after 60 seconds.

This is implemented as an `@app.middleware("http")` decorator in `app/api/main.py` using
an in-process `defaultdict(list)` — no external rate-limit service required.

**Limitation:** the counter resets on API restart and is not shared across multiple
API replicas. For multi-replica deployments, use Redis-backed rate limiting (e.g. slowapi).

---

## Non-Root Containers

All application containers (`api`, `worker`, `sftp-ingest`) run as a dedicated non-root user:

```dockerfile
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /sbin/nologin appuser
USER appuser
```

The `migrate` container runs as root — acceptable for a transient init container with no
exposed ports and no persistent state.

---

## CORS

The API allows cross-origin requests only from origins listed in `CORS_ORIGINS` (comma-separated).

```
Default: http://localhost:3000  (local React dev server)
Override: CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

`allow_credentials=True` with a wildcard origin (`*`) is rejected by the browser security spec
and would break authentication. The allowlist approach is the only correct implementation.

---

## Model Integrity

At startup, the API and worker verify the classifier weights:

1. `app/classifier/models/classifier.pt` must exist.
2. `app/classifier/models/model_card.json` must exist.
3. SHA-256 of the `.pt` file must match `model_card.json["sha256"]`.
4. `model_card.json["test_top1"]` must be ≥ 0.85.

If any check fails, the container refuses to start with a clear error message.
Set `DEV_SKIP_MODEL_CHECK=1` in `.env` only during local development before weights are trained.

---

## Audit Log

Every privileged action writes an immutable record to the `audit_logs` table:

| Action | Trigger |
|--------|---------|
| `user_create` | Admin creates a new user |
| `role_change` | Admin changes a user's role |
| `relabel` | Reviewer corrects an AI prediction |

The audit log is append-only — there are no `UPDATE` or `DELETE` operations on it.
