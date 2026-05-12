# Phase 2: Database — Schema and Migrations

## What Is This Phase?

This phase defines **what data the system stores** and **how the database tables are created/updated**. We use PostgreSQL as our database and Alembic as our migration tool.

---

## Key Concepts for Beginners

### What Is a Database Table?
A table is like a spreadsheet — rows are records, columns are fields.

```
users table:
┌────┬──────────────────────┬───────────┬──────────────────────┐
│ id │ email                │ role      │ created_at           │
├────┼──────────────────────┼───────────┼──────────────────────┤
│  1 │ alice@example.com    │ admin     │ 2026-05-10 09:00:00  │
│  2 │ bob@example.com      │ reviewer  │ 2026-05-10 10:00:00  │
│  3 │ carol@example.com    │ auditor   │ 2026-05-11 14:30:00  │
└────┴──────────────────────┴───────────┴──────────────────────┘
```

### What Is SQLAlchemy?
SQLAlchemy is a Python library that lets you define database tables as Python classes. Instead of writing raw SQL, you write Python. SQLAlchemy translates it to SQL for you.

### What Is Alembic?
Alembic is a tool that manages **database schema changes over time**. When you need to add a new column or create a new table, you write an Alembic "migration" script. Alembic tracks which migrations have run and applies only the new ones.

Think of it like version control (git) but for your database schema.

---

## Files in This Directory

```
app/db/
├── README.md      ← you are here
├── __init__.py    ← makes this a Python package
├── models.py      ← SQLAlchemy ORM table definitions
└── session.py     ← creates the database connection
```

---

## models.py — The Database Tables

This file defines **5 tables**:

### 1. `users` — Who Can Use the System
```python
id          UUID, primary key
email       string, unique
hashed_password  string (never store plain passwords!)
role        string: "admin" | "reviewer" | "auditor"
is_active   boolean
created_at  timestamp
```

### 2. `batches` — Groups of Documents
When the SFTP watcher picks up files, it groups them into a "batch" (one batch per drop).
```python
id          UUID, primary key
status      string: "pending" | "processing" | "done" | "failed"
created_at  timestamp
updated_at  timestamp
```

### 3. `predictions` — AI Results
One row per document, storing what the AI predicted.
```python
id              UUID, primary key
batch_id        UUID, foreign key → batches.id
filename        string (original file name)
blob_key        string (path in MinIO where the file lives)
overlay_key     string (path in MinIO for the annotated overlay)
predicted_class string (e.g. "invoice")
confidence      float (0.0 to 1.0)
relabeled_class string | null (if a reviewer corrected the AI)
relabeled_by    UUID | null (who made the correction)
created_at      timestamp
```

### 4. `audit_log` — Who Did What
Every important action is recorded here for accountability.
```python
id         UUID, primary key
actor_id   UUID (who did it)
action     string (e.g. "role_change", "relabel", "batch_state_change")
target     string (what was affected, e.g. a user ID or batch ID)
detail     JSON (extra context)
created_at timestamp
```

### 5. `casbin_rule` — Permission Rules
Casbin (the permission library) stores its rules in this table.
```python
id    integer, primary key
ptype string (policy type)
v0    string (role, e.g. "admin")
v1    string (resource, e.g. "/batches")
v2    string (action, e.g. "GET")
```

---

## session.py — The Database Connection

This file creates the SQLAlchemy "engine" (the connection to PostgreSQL) and the "session factory" (used to start transactions).

The database URL is **not hardcoded** — it is fetched from HashiCorp Vault at startup. If Vault is unreachable, the app refuses to start.

```python
# Conceptually what session.py does:
db_url = vault.get_secret("database/url")   # fetched from Vault
engine = create_engine(db_url)
SessionLocal = sessionmaker(engine)
```

---

## Alembic Migrations

Migrations live in the `alembic/` folder at the project root (not inside `app/db/`).

### How Migrations Work

```bash
# Create a new migration after you change models.py
alembic revision --autogenerate -m "add overlay_key column"

# Apply all pending migrations (runs in the 'migrate' Docker container)
alembic upgrade head

# See what migrations have been applied
alembic history
```

### The `migrate` Container

In `docker-compose.yml`, there is a `migrate` service that:
1. Connects to PostgreSQL.
2. Runs `alembic upgrade head` to apply all pending migrations.
3. **Exits** — it is not a long-running service.
4. Only after `migrate` exits successfully does the `api` container start.

This ensures the database schema is always up-to-date before the API starts serving requests.

---

## Important Architecture Rule

**`models.py` is only imported by files in `app/repositories/`.**

No other part of the codebase (not routers, not services) should import SQLAlchemy models directly. This enforces separation of concerns — the database layer is isolated.

```
app/api/routers/    ← HTTP only, NO direct DB access
app/services/       ← business logic, NO direct DB access
app/repositories/   ← ONLY place that imports models.py ✓
app/db/models.py    ← defines the tables
```

---

## What You Need to Know for the Presentation

- What is a database migration and why do we use Alembic instead of manually writing `CREATE TABLE`?
  - Answer: migrations are version-controlled SQL changes that can be applied/rolled back safely
- Why is the password stored as `hashed_password` and not `password`?
  - Answer: you never store plain text passwords; if the DB leaks, hashed passwords can't be reversed
- Why does `migrate` exit after running migrations?
  - Answer: it's a one-time setup job, not a service — like a constructor that runs once
- Why does the audit log have a `detail` JSON column?
  - Answer: flexible extra context without needing new columns for every action type
