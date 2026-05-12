# Phase 5: Services — Business Logic Layer

## What Is This Phase?

Services are the **brain of the application**. They sit between the HTTP layer (routers) and the data layer (repositories), and they own all business logic.

If the routers are the front door and the repositories are the filing cabinet, the services are the office manager who decides what to do with incoming requests.

---

## What "Business Logic" Means

Business logic is any decision the application makes:
- "Before creating a user, hash their password."
- "Only allow relabeling if the confidence is below 0.7."
- "When a role changes, write to the audit log and invalidate the user's cache."
- "If the user is the last admin, block the role change."

None of this logic belongs in routers (HTTP layer) or repositories (database layer). It all lives here.

---

## The Rules for Services

1. **Services own transaction boundaries** — they decide when to commit or roll back. If you need to write to two tables atomically (e.g., update a prediction AND write to audit log), the service wraps both in a single transaction.

2. **Services own cache invalidation** — when a write makes cached data stale, the service calls the cache to invalidate it. Routers and repositories do not touch the cache.

3. **Services call repositories** — services never write SQL directly. They call repository methods.

4. **Services never raise HTTP errors** — they raise domain-level exceptions (`PermissionError`, `ValueError`). The router catches these and translates them to HTTP status codes.

---

## Files in This Directory

```
app/services/
├── README.md              ← you are here
├── __init__.py
├── user_service.py        ← user creation, role changes
├── batch_service.py       ← batch creation and status management
└── prediction_service.py  ← prediction writing, relabeling
```

---

## user_service.py

```python
class UserService:
    def __init__(self, user_repo, audit_repo, cache):
        self.user_repo  = user_repo
        self.audit_repo = audit_repo
        self.cache      = cache

    async def create_user(self, email: str, password: str, role: str,
                          actor: User) -> User:
        # 1. Only admins can create users
        if actor.role != "admin":
            raise PermissionError("Only admins can create users")

        # 2. Hash the password (never store plain text)
        hashed = hash_password(password)

        # 3. Write to DB
        user = await self.user_repo.create(email, hashed, role)

        # 4. Write to audit log
        await self.audit_repo.insert(
            actor_id=actor.id,
            action="user_create",
            target=str(user.id),
            detail={"email": email, "role": role}
        )
        return user

    async def change_role(self, target_user_id: UUID, new_role: str,
                          actor: User) -> User:
        # 1. Only admins can change roles
        if actor.role != "admin":
            raise PermissionError("Only admins can change roles")

        # 2. If the target is an admin, make sure we're not removing the last one
        target = await self.user_repo.get_by_id(target_user_id)
        if target.role == "admin" and new_role != "admin":
            admin_count = await self.user_repo.count_by_role("admin")
            if admin_count == 1:
                raise ValueError("Cannot demote the last admin")

        # 3. Update role in DB
        updated = await self.user_repo.update_role(target_user_id, new_role)

        # 4. Invalidate the user's cache (their permissions update on next request)
        await self.cache.delete(f"user:{target_user_id}")

        # 5. Write audit log
        await self.audit_repo.insert(
            actor_id=actor.id,
            action="role_change",
            target=str(target_user_id),
            detail={"from": target.role, "to": new_role}
        )
        return updated
```

---

## batch_service.py

```python
class BatchService:
    async def create_batch(self) -> Batch:
        # Creates a new batch in "pending" state
        batch = await self.batch_repo.create()
        await self.cache.delete("batches:list")  # list is now stale
        return batch

    async def mark_processing(self, batch_id: UUID) -> Batch:
        batch = await self.batch_repo.update_status(batch_id, "processing")
        await self._invalidate_batch_cache(batch_id)
        await self.audit_repo.insert(
            actor_id=None,   # system action, no human actor
            action="batch_state_change",
            target=str(batch_id),
            detail={"to": "processing"}
        )
        return batch

    async def mark_done(self, batch_id: UUID) -> Batch:
        batch = await self.batch_repo.update_status(batch_id, "done")
        await self._invalidate_batch_cache(batch_id)
        await self.audit_repo.insert(...)
        return batch

    async def _invalidate_batch_cache(self, batch_id: UUID):
        # Invalidate both the specific batch and the list
        await self.cache.delete(f"batch:{batch_id}")
        await self.cache.delete("batches:list")
```

---

## prediction_service.py

```python
class PredictionService:
    async def save_prediction(self, batch_id: UUID, filename: str,
                              blob_key: str, overlay_key: str,
                              predicted_class: str, confidence: float) -> Prediction:
        pred = await self.prediction_repo.create(
            batch_id, filename, blob_key, overlay_key,
            predicted_class, confidence
        )
        await self.cache.delete("predictions:recent")
        return pred

    async def relabel(self, prediction_id: UUID,
                      new_class: str, actor: User) -> Prediction:
        # 1. Only reviewers can relabel
        if actor.role not in ("admin", "reviewer"):
            raise PermissionError("Only reviewers can relabel predictions")

        # 2. Get the prediction to check confidence
        pred = await self.prediction_repo.get_by_id(prediction_id)
        if pred is None:
            raise ValueError("Prediction not found")

        # 3. Reviewers can only relabel low-confidence predictions
        if actor.role == "reviewer" and pred.confidence >= 0.7:
            raise PermissionError(
                "Reviewers can only relabel predictions with confidence < 0.7"
            )

        # 4. Apply the relabel
        updated = await self.prediction_repo.relabel(prediction_id, new_class, actor.id)

        # 5. Invalidate relevant caches
        await self.cache.delete("predictions:recent")
        await self.cache.delete(f"batch:{pred.batch_id}")

        # 6. Audit log
        await self.audit_repo.insert(
            actor_id=actor.id,
            action="relabel",
            target=str(prediction_id),
            detail={"from": pred.predicted_class, "to": new_class}
        )
        return updated
```

---

## How Dependency Injection Works

Services receive their dependencies (repositories, cache) through their constructor. This makes them easy to test: in tests, you pass in fake repositories instead of real ones.

```python
# In the router, FastAPI builds the service with real dependencies:
async def get_user_service(
    db:    AsyncSession      = Depends(get_db),
    cache: CacheClient       = Depends(get_cache),
) -> UserService:
    user_repo  = UserRepository(db)
    audit_repo = AuditRepository(db)
    return UserService(user_repo, audit_repo, cache)

# In tests, you can pass fake implementations:
service = UserService(
    user_repo  = FakeUserRepo(),
    audit_repo = FakeAuditRepo(),
    cache      = FakeCache(),
)
```

---

## Cache Invalidation Strategy

When data changes, we delete the stale cache key. The next request will miss the cache, hit the database, and cache the fresh result.

```
Write happens (e.g. role change)
         |
service.change_role() is called
         |
user_repo.update_role()  ← writes to DB
         |
cache.delete("user:{id}")  ← removes stale cache entry
         |
Next GET /me request
         |
cache miss → load from DB → cache fresh result
```

This is called **cache-aside** or **lazy loading**. The cache is never written directly after a mutation — it is populated only on the next read miss.

---

## What You Need to Know for the Presentation

- Why can't the router handle business logic directly?
  - Answer: routers should only handle HTTP concerns (parsing requests, returning responses); business rules belong in a single place that can be tested and reused
- Why does cache invalidation live in the service layer?
  - Answer: the service knows what changed and what is now stale; the router and repository don't have enough context
- What is a transaction boundary?
  - Answer: a transaction groups multiple DB operations so they either all succeed or all fail — the service decides the boundary
- What happens if the audit log write fails after the role change succeeds?
  - Answer: both are wrapped in the same transaction — if the audit write fails, the role change is rolled back too
- Why can't the last admin demote themselves?
  - Answer: you'd lock out all admin access; the system would have no one to restore it
