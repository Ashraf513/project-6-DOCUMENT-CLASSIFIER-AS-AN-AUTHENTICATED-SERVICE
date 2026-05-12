# Phase 3: Domain — Data Shapes (Pydantic Models)

## What Is This Phase?

This phase defines **what your data looks like in Python code** — not in the database, not in HTTP responses, but as pure Python objects that carry data between layers of the application.

These are called **domain models** and they use Pydantic for validation.

---

## Key Concept: Why Two Sets of Models?

The project has **two different model systems** that look similar but serve different purposes:

| | SQLAlchemy Models (`app/db/models.py`) | Pydantic Domain Models (`app/domain/`) |
|---|---|---|
| **Lives in** | `app/db/` | `app/domain/` |
| **Purpose** | Maps to database tables | Carries data in Python code |
| **Used by** | Repositories only | Services, API, workers |
| **Validates data?** | No | Yes (Pydantic validates automatically) |
| **Can have DB logic?** | Yes (relationships, columns) | No |

**Why separate them?** If your API response model and your database model are the same object, you risk accidentally exposing database fields that should be private (like `hashed_password`). Keeping them separate means you control exactly what leaves each layer.

---

## What Is Pydantic?

Pydantic is a Python library for **data validation**. You define a class with typed fields, and Pydantic automatically:
- Checks that required fields are present.
- Validates that values are the right type (e.g., email must look like an email).
- Converts types where needed (e.g., string `"true"` → boolean `True`).

```python
from pydantic import BaseModel

class User(BaseModel):
    email: str
    role: str

# This works:
u = User(email="alice@example.com", role="admin")

# This raises a ValidationError immediately:
u = User(email=123, role="admin")  # email must be a string
```

---

## Files in This Directory

```
app/domain/
├── README.md       ← you are here
├── __init__.py     ← makes this a Python package
├── user.py         ← user-related domain models
├── batch.py        ← batch-related domain models
└── prediction.py   ← prediction-related domain models
```

---

## user.py — User Domain Models

These models represent users as they flow through the application (not as database rows).

```python
class UserRole(str, Enum):
    admin    = "admin"
    reviewer = "reviewer"
    auditor  = "auditor"

class User(BaseModel):
    id:         UUID
    email:      EmailStr      # Pydantic validates it looks like an email
    role:       UserRole
    is_active:  bool
    created_at: datetime

class UserCreate(BaseModel):
    email:    EmailStr
    password: str             # plain text — only used for registration input
    role:     UserRole = UserRole.auditor  # default role

class UserUpdate(BaseModel):
    role: UserRole            # only admins can update roles
```

Notice: `User` (what you return) does NOT have `password` or `hashed_password`. `UserCreate` (what you receive) has `password` but the service hashes it immediately — the plain text never hits the database.

---

## batch.py — Batch Domain Models

A "batch" is a group of documents dropped into SFTP at the same time.

```python
class BatchStatus(str, Enum):
    pending    = "pending"     # files received, not yet processed
    processing = "processing"  # AI worker is running
    done       = "done"        # all predictions written
    failed     = "failed"      # something went wrong

class Batch(BaseModel):
    id:         UUID
    status:     BatchStatus
    created_at: datetime
    updated_at: datetime
    file_count: int           # how many documents in this batch

class BatchSummary(BaseModel):
    id:         UUID
    status:     BatchStatus
    created_at: datetime
    file_count: int
    # used for the list endpoint — less detail than the full Batch
```

---

## prediction.py — Prediction Domain Models

One prediction per document — the AI's answer.

```python
class Prediction(BaseModel):
    id:              UUID
    batch_id:        UUID
    filename:        str        # original file name
    blob_key:        str        # path in MinIO to the original file
    overlay_key:     str        # path in MinIO to the annotated image
    predicted_class: str        # what the AI said (e.g. "invoice")
    confidence:      float      # how sure the AI was (0.0–1.0)
    relabeled_class: str | None # what a reviewer corrected it to
    relabeled_by:    UUID | None
    created_at:      datetime

class PredictionRelabel(BaseModel):
    new_class: str              # the corrected label from a reviewer

    @validator("new_class")
    def must_be_valid_class(cls, v):
        valid = {"letter", "form", "email", ...}  # all 16 classes
        if v not in valid:
            raise ValueError(f"{v} is not a valid document class")
        return v
```

---

## Data Flow Across Layers

Here is how data moves from the database through domain models to the HTTP response:

```
Database row (SQLAlchemy)
         |
         | repository reads it, converts to domain model
         v
Domain Model (Pydantic)
         |
         | service applies business logic
         v
Domain Model (possibly modified)
         |
         | router serializes to JSON
         v
HTTP Response (JSON)
```

Each arrow is a transformation — no raw database objects leak to the HTTP layer.

---

## What You Need to Know for the Presentation

- Why do we have domain models separate from SQLAlchemy models?
  - Answer: isolation — changes to DB schema don't automatically change the API contract
- Why use Pydantic instead of plain Python dataclasses?
  - Answer: automatic validation — bad data is rejected at the boundary, not silently passed through
- Why does `UserCreate` have `password` but `User` does not?
  - Answer: `UserCreate` is input (from the client), `User` is output (to the client); we never return passwords
- What is an `Enum` and why use it for roles and statuses?
  - Answer: prevents typos — you can't set `role = "admine"` if the Enum only has `"admin"`
