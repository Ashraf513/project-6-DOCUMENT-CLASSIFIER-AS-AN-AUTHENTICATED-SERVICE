# Phase 4: Repositories — Data Access Layer

## What Is This Phase?

Repositories are the **only part of the codebase that reads from and writes to the database**. Every database query lives here — nowhere else.

If you need data from the database, you call a repository. If you need to update a record, you call a repository. Repositories do nothing else.

---

## Key Concept: Why Have a Repository Layer?

Without repositories, you might have database queries scattered throughout your code:
```python
# BAD — query inside a router (this is what we prevent)
@router.get("/batches")
async def list_batches(db: Session = Depends(get_db)):
    return db.query(Batch).filter(Batch.status == "done").all()
```

With repositories, the router calls a function instead:
```python
# GOOD — router calls a repository function
@router.get("/batches")
async def list_batches(batch_repo: BatchRepo = Depends()):
    return await batch_repo.list_done()
```

**Benefits:**
- All SQL is in one predictable place — easy to audit and optimize.
- You can unit-test the repository independently.
- Changing from PostgreSQL to another database only requires changing repositories.
- The router has no idea SQL even exists.

---

## The Rules for Repositories

Repositories must follow three strict rules:

1. **No HTTP errors** — repositories never raise `HTTPException` or anything from FastAPI. They raise plain Python exceptions like `ValueError` or `KeyError`. The service layer decides what to do with those.

2. **No cache invalidation** — repositories never touch Redis. If a write should invalidate a cache entry, that logic lives in the service layer.

3. **Only import from `app/db/models.py`** — repositories work with SQLAlchemy ORM objects and return domain models. They do not return raw SQL rows.

---

## Files in This Directory

```
app/repositories/
├── README.md           ← you are here
├── __init__.py
├── user_repo.py        ← CRUD for users
├── batch_repo.py       ← CRUD for batches
├── prediction_repo.py  ← CRUD for predictions
└── audit_repo.py       ← insert-only audit log
```

---

## user_repo.py

```python
class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        # SELECT * FROM users WHERE id = ?
        ...

    async def get_by_email(self, email: str) -> User | None:
        # SELECT * FROM users WHERE email = ?
        ...

    async def create(self, email: str, hashed_password: str, role: str) -> User:
        # INSERT INTO users (...) VALUES (...)
        ...

    async def update_role(self, user_id: UUID, new_role: str) -> User:
        # UPDATE users SET role = ? WHERE id = ?
        ...

    async def list_all(self) -> list[User]:
        # SELECT * FROM users
        ...
```

Notice: the repository receives `hashed_password` — the hashing happens in the service layer before this is called.

---

## batch_repo.py

```python
class BatchRepository:
    async def create(self) -> Batch:
        # INSERT INTO batches (status='pending') VALUES (...)
        ...

    async def get_by_id(self, batch_id: UUID) -> Batch | None:
        # SELECT * FROM batches WHERE id = ?
        ...

    async def list_all(self, limit: int = 50) -> list[BatchSummary]:
        # SELECT * FROM batches ORDER BY created_at DESC LIMIT ?
        ...

    async def update_status(self, batch_id: UUID, status: str) -> Batch:
        # UPDATE batches SET status = ?, updated_at = NOW() WHERE id = ?
        ...
```

---

## prediction_repo.py

```python
class PredictionRepository:
    async def create(self, batch_id: UUID, filename: str,
                     blob_key: str, predicted_class: str,
                     confidence: float) -> Prediction:
        # INSERT INTO predictions (...) VALUES (...)
        ...

    async def list_by_batch(self, batch_id: UUID) -> list[Prediction]:
        # SELECT * FROM predictions WHERE batch_id = ?
        ...

    async def list_recent(self, limit: int = 20) -> list[Prediction]:
        # SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?
        ...

    async def relabel(self, prediction_id: UUID,
                      new_class: str, relabeled_by: UUID) -> Prediction:
        # UPDATE predictions SET relabeled_class = ?, relabeled_by = ? WHERE id = ?
        ...
```

---

## audit_repo.py

The audit log is **append-only** — you can insert records and read them, but never update or delete them. This is intentional: the audit trail must be immutable.

```python
class AuditRepository:
    async def insert(self, actor_id: UUID, action: str,
                     target: str, detail: dict) -> None:
        # INSERT INTO audit_log (actor_id, action, target, detail) VALUES (...)
        ...

    async def list_recent(self, limit: int = 100) -> list[AuditEntry]:
        # SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?
        ...
```

**Actions that always get logged:**
- `role_change` — when an admin changes someone's role
- `relabel` — when a reviewer corrects an AI prediction
- `batch_state_change` — when a batch moves from pending → processing → done

---

## How Sessions Work

Each HTTP request gets its own database session (connection). SQLAlchemy uses async sessions to avoid blocking the event loop.

```python
# This is how a repository gets its database session (simplified):
# The session is created per-request and closed when the request ends.
# If an exception occurs, the session rolls back automatically.

async def get_db():
    async with SessionLocal() as session:
        yield session          # request runs here
        await session.commit() # commit on success
        # rollback happens automatically on exception
```

The session is injected via FastAPI's dependency injection system (`Depends`).

---

## Example: What Happens When You Create a User

```
1. router receives POST /users request
2. router calls user_service.create_user(email, password, role)
3. service hashes the password
4. service calls user_repo.create(email, hashed_password, role)
5. repository runs INSERT INTO users
6. repository converts the ORM object → domain model
7. repository returns User domain model to service
8. service writes to audit log (audit_repo.insert)
9. service returns User to router
10. router serializes User → JSON response
```

---

## What You Need to Know for the Presentation

- What is the repository pattern and why does it help?
  - Answer: single place for all SQL — easy to find, test, and change database logic
- Why must repositories never raise `HTTPException`?
  - Answer: repositories don't know they're in an HTTP context — they could be called from CLI tools, workers, or tests
- Why is the audit log append-only?
  - Answer: if you could delete audit log entries, the system could hide unauthorized actions
- What does the repository return — ORM objects or domain models?
  - Answer: domain models — the ORM objects stay inside the repository
