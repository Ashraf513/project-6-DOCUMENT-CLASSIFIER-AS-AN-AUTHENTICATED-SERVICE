# Phase 6: API — HTTP Endpoints

## What Is This Phase?

This is the **front door** of the application. The API layer exposes HTTP endpoints that authenticated users call to interact with the system.

It is built with **FastAPI**, a modern Python web framework that automatically generates interactive documentation and validates request/response data.

---

## Key Concept: What Is an HTTP API?

An HTTP API is a set of URLs that clients can call to send or receive data.

```
Client (browser, curl, other service)
         |
         | HTTP Request: GET /batches
         |               Authorization: Bearer <token>
         v
[FastAPI Router] → [Service] → [Repository] → [Database]
         |
         | HTTP Response: 200 OK
         |               {"batches": [...]}
         v
Client receives JSON data
```

---

## What FastAPI Gives Us

- **Automatic docs** at `http://localhost:8000/docs` — a web interface to try every endpoint.
- **Automatic request validation** — if you send the wrong data type, FastAPI rejects it immediately.
- **Async support** — FastAPI handles many requests at the same time without blocking.
- **Dependency injection** — services, database sessions, and the current user are "injected" into route handlers automatically.

---

## Files in This Directory

```
app/api/
├── README.md         ← you are here
├── __init__.py
├── main.py           ← creates the FastAPI app, registers routers
├── deps.py           ← shared dependencies (get current user, get DB session, etc.)
└── routers/
    ├── __init__.py
    ├── auth.py       ← login, registration, token refresh
    ├── users.py      ← user management (admin only)
    ├── batches.py    ← list batches, get batch detail
    └── predictions.py ← view predictions, relabel
```

---

## main.py — The Application Entry Point

```python
from fastapi import FastAPI
from app.api.routers import auth, users, batches, predictions

app = FastAPI(title="Document Classifier API")

# Register all routers with their URL prefixes
app.include_router(auth.router,        prefix="/auth")
app.include_router(users.router,       prefix="/users")
app.include_router(batches.router,     prefix="/batches")
app.include_router(predictions.router, prefix="/predictions")

@app.on_event("startup")
async def startup():
    # 1. Connect to Vault, load JWT signing key
    # 2. Verify classifier weights + SHA-256
    # 3. Verify Casbin policy table is not empty
    # If any check fails → raise exception → app refuses to start
    ...
```

---

## deps.py — Shared Dependencies

Dependencies are reusable functions that FastAPI calls automatically for each request.

```python
async def get_db() -> AsyncSession:
    # Yields a database session, commits on success, rolls back on error
    ...

async def get_current_user(token: str = Depends(oauth2_scheme),
                           db: AsyncSession = Depends(get_db)) -> User:
    # Decodes the JWT token, looks up the user in the database
    # Raises 401 if token is invalid or expired
    ...

async def require_admin(user: User = Depends(get_current_user)) -> User:
    # Raises 403 if the user is not an admin
    ...

async def require_reviewer(user: User = Depends(get_current_user)) -> User:
    # Raises 403 if the user is not admin or reviewer
    ...
```

---

## routers/auth.py — Authentication Endpoints

| Method | URL | What It Does |
|--------|-----|--------------|
| POST | `/auth/register` | Create a new account (email + password) |
| POST | `/auth/login` | Log in, receive a JWT token |
| POST | `/auth/refresh` | Get a new token before the old one expires |
| GET | `/auth/me` | Get your own user info (cached) |

```python
@router.post("/login")
async def login(credentials: LoginRequest,
                user_service: UserService = Depends(get_user_service)):
    # 1. Look up user by email
    # 2. Verify password matches stored hash
    # 3. Create a JWT token signed with the key from Vault
    # 4. Return {"access_token": "...", "token_type": "bearer"}
    ...

@router.get("/me")
@cache(expire=300)  # cache for 5 minutes
async def get_me(user: User = Depends(get_current_user)):
    return user
```

**What is a JWT token?**
JWT (JSON Web Token) is a signed string that proves who you are. It looks like: `eyJhb...`. After login, you include it in every request as a header: `Authorization: Bearer eyJhb...`. The server verifies the signature to trust it without checking the database every time.

---

## routers/users.py — User Management (Admin Only)

| Method | URL | Who Can Call | What It Does |
|--------|-----|-------------|--------------|
| POST | `/users/invite` | admin | Create a new user account |
| GET | `/users/` | admin | List all users |
| PATCH | `/users/{id}/role` | admin | Change a user's role |
| GET | `/users/audit-log` | admin | View all audit log entries |

```python
@router.patch("/{user_id}/role")
async def change_role(
    user_id: UUID,
    body: RoleUpdate,
    actor: User = Depends(require_admin),
    user_service: UserService = Depends(get_user_service),
):
    # The router only calls the service — no business logic here
    updated = await user_service.change_role(user_id, body.role, actor)
    return updated
```

Notice: the router calls `user_service.change_role()` and immediately returns the result. All the checks (last admin guard, audit log, cache invalidation) happen inside the service.

---

## routers/batches.py — Batch Browsing

| Method | URL | Who Can Call | What It Does |
|--------|-----|-------------|--------------|
| GET | `/batches` | reviewer, auditor, admin | List all batches |
| GET | `/batches/{id}` | reviewer, auditor, admin | Get one batch with predictions |

```python
@router.get("/")
@cache(expire=60)  # cached for 1 minute
async def list_batches(
    user: User = Depends(require_reviewer_or_auditor),
    batch_service: BatchService = Depends(get_batch_service),
):
    return await batch_service.list_batches()

@router.get("/{batch_id}")
@cache(expire=60)
async def get_batch(
    batch_id: UUID,
    user: User = Depends(require_reviewer_or_auditor),
    batch_service: BatchService = Depends(get_batch_service),
):
    batch = await batch_service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch
```

Note: `HTTPException` (the HTTP-specific error) is raised **in the router**, not in the service.

---

## routers/predictions.py — Predictions

| Method | URL | Who Can Call | What It Does |
|--------|-----|-------------|--------------|
| GET | `/predictions/recent` | reviewer, auditor, admin | Last 20 predictions |
| PATCH | `/predictions/{id}/relabel` | reviewer, admin | Correct an AI prediction |

```python
@router.patch("/{prediction_id}/relabel")
async def relabel(
    prediction_id: UUID,
    body: PredictionRelabel,
    actor: User = Depends(require_reviewer),
    pred_service: PredictionService = Depends(get_prediction_service),
):
    try:
        updated = await pred_service.relabel(prediction_id, body.new_class, actor)
        return updated
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

The router translates service exceptions → HTTP status codes. This is the only place that should do this translation.

---

## The Cache Layer (fastapi-cache2)

We use `fastapi-cache2` to cache responses in Redis. The `@cache(expire=N)` decorator stores the response for N seconds.

```
First request to GET /batches:
  cache MISS → calls batch_service.list_batches() → hits DB → stores in Redis
  response time: ~100ms

Second request to GET /batches (within 60 seconds):
  cache HIT → returns from Redis directly (no DB call)
  response time: ~5ms
```

When a batch changes state, the service calls `cache.delete("batches:list")`, so the next request gets fresh data.

---

## Authentication Flow (Full Example)

```bash
# Step 1: Register
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "secret123"}'

# Step 2: Login → get token
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -d "username=alice@example.com&password=secret123" | jq -r .access_token)

# Step 3: Call authenticated endpoints
curl http://localhost:8000/batches \
  -H "Authorization: Bearer $TOKEN"
```

---

## What You Need to Know for the Presentation

- What does the router's job start and end with?
  - Answer: starts at parsing the HTTP request, ends at returning the HTTP response — nothing else
- Why does the router raise `HTTPException` but the service doesn't?
  - Answer: `HTTPException` is HTTP-specific; services should be usable from CLI tools or workers too
- What is a JWT token and why is the signing key stored in Vault?
  - Answer: JWT is a signed token proving identity; the signing key is a secret that must not be hardcoded
- How does caching improve performance?
  - Answer: cached reads skip the database entirely, going from ~100ms to ~5ms
- What is dependency injection in FastAPI?
  - Answer: FastAPI calls `Depends(...)` functions automatically before calling your route handler, injecting the result
