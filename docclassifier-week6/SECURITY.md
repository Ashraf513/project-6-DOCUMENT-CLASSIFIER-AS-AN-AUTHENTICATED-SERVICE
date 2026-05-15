# Security Model

---

## Authentication

**Mechanism:** JWT (JSON Web Token) via fastapi-users with Bearer transport.

- Tokens are signed with `JWT_SECRET` fetched from Vault at startup.
- Default lifetime: 86 400 s (24 h), configurable via `JWT_LIFETIME_SECONDS`.
- The secret is never stored in code, git history, or `.env` files — only in Vault.

**Login rate limiting:** The `/auth/jwt/login` endpoint is protected by an in-process
rate limiter: 5 failed attempts per 60-second window per source IP. Excess attempts
receive HTTP 429. The store is in-memory and resets on API restart (sufficient for
single-instance deployments; add Redis-backed rate limiting for multi-instance).

---

## Authorization

**Mechanism:** Casbin policy-based RBAC with the SQLAlchemy adapter.

Three roles:

| Role | Capabilities |
|---|---|
| `admin` | Full access: user management, upload, relabel (any confidence), audit log |
| `reviewer` | Read batches/predictions, upload, relabel predictions with confidence < 0.7 |
| `auditor` | Read-only: batches, predictions, audit log; no upload or relabel |

Every protected route calls `enforcer.enforce(actor.role.value, endpoint, method)`.
A 403 is returned if the check fails; the policy is never bypassed.

**Confidence threshold for reviewers:** Enforced at the service layer
(`PredictionService.relabel`), not only at the API layer — even direct DB access
through the service cannot circumvent it.

**Last-admin guard:** `UserService.change_role` and `UserService.delete_user` both count
current admins before allowing a demotion or deletion that would leave zero admins.

**Self-deletion prevention:** `UserService.delete_user` rejects requests where
`target_user_id == actor.id`.

---

## Password storage

Algorithm: **Argon2id** (memory-hard, side-channel-resistant) via `pwdlib[argon2]`.

`hash_password()` and `verify_password()` in `app/infra/security.py` wrap pwdlib.
`UserService.create_user()` hashes the plain-text password before persisting.
Plain-text passwords are never logged or stored.

---

## Secret management

All application secrets are stored in HashiCorp Vault KV-v2:

| Secret key | Used for |
|---|---|
| `JWT_SECRET` | JWT signing |
| `MINIO_ACCESS_KEY` | MinIO authentication |
| `MINIO_SECRET_KEY` | MinIO authentication |
| `SFTP_USER` | SFTP server login |
| `SFTP_PASSWORD` | SFTP server login |

**Docker Compose dev flow:**
1. `vault` starts in dev mode (data in-memory, auto-unsealed).
2. `vault-init` seeds the secrets via `vault kv put secret/docclassifier ...`.
3. `JWT_SECRET` is generated with `dd if=/dev/urandom bs=48 count=1 | base64` at
   each fresh start — tokens from a previous run are always invalidated on restart.

**Local dev without Vault (`DEV_MODE=1`):**
The same keys are read from environment variables. Never set `DEV_MODE=1` in production.

---

## Transport security

- In development: all service-to-service communication is on the isolated `backend`
  Docker bridge network; no TLS is required within that network.
- In production: place the API behind a TLS-terminating reverse proxy (nginx, Caddy,
  AWS ALB). The API itself does not handle TLS.
- CORS: `CORSMiddleware` is configured with explicit allowed origins via `CORS_ORIGINS`
  env var. Wildcard `*` with `allow_credentials=True` is rejected by browsers — the
  env var must be set to the actual frontend origin.

---

## SFTP security

The SFTP server (`atmoz/sftp`) uses password authentication in development.
For production:
- Replace password auth with SSH public-key auth.
- Pin the server host key in `SFTPWatcher._SFTPSession` (replace `AutoAddPolicy`
  with a `HostKeys` instance loaded from a known-hosts file).
- Use a dedicated scanner-vendor account with write-only permissions to `/upload`.

---

## Audit trail

Every state-changing operation writes an immutable entry to `audit_logs`:

| Action | Trigger |
|---|---|
| `user_create` | Admin creates a new user |
| `role_change` | Admin changes a user's role |
| `user_deleted` | Admin deletes a user (actor_id preserved even if actor later deleted) |
| `batch_created` | New batch created by sftp-ingest or HTTP upload |
| `batch_state_change` | Batch transitions between status values |
| `relabel` | Reviewer or admin relabels a prediction |

Audit entries are written inside the same database transaction as the mutation. If the
mutation rolls back, the audit entry is also rolled back. The `actor_id` FK uses
`ON DELETE SET NULL` — deleting a user does not erase their audit history.

---

## Security scan checklist

| Check | Status |
|---|---|
| No hardcoded `JWT_SECRET` | ✅ Fetched from Vault; env fallback only in DEV_MODE |
| No hardcoded MinIO credentials | ✅ Fetched from Vault |
| No hardcoded SFTP credentials | ✅ Fetched from Vault |
| Plain-text passwords never stored | ✅ Argon2id hash only |
| SQL injection | ✅ SQLAlchemy parameterised queries throughout |
| RBAC enforced per route | ✅ Casbin enforcer called in every protected handler |
| Rate limiting on login | ✅ 5 attempts / 60 s / IP |
| CORS origins explicit | ✅ `CORS_ORIGINS` env var required |
| Secrets not in git | ✅ `.env` in `.gitignore`; Vault for runtime |
| Model weights integrity | ✅ SHA-256 + top-1 accuracy checked at startup |
