# Document Classifier — Week 6 Project

## What Is This?

This project builds a **document classification service** that automatically identifies what type a scanned document is (invoice, resume, letter, etc.) using an AI model.

Think of it like a smart filing cabinet: you drop a scanned document in one end, and the system reads it, decides what category it belongs to, and stores that result — all without any human involvement.

---

## The 16 Document Types It Recognizes

| # | Class | Example |
|---|-------|---------|
| 0 | letter | Business correspondence |
| 1 | form | Fill-in forms |
| 2 | email | Printed emails |
| 3 | handwritten | Handwritten notes |
| 4 | advertisement | Flyers, ads |
| 5 | scientific report | Lab reports |
| 6 | scientific publication | Journal papers |
| 7 | specification | Technical specs |
| 8 | file folder | Folder cover sheets |
| 9 | news article | Newspaper clippings |
| 10 | budget | Financial tables |
| 11 | invoice | Bills |
| 12 | presentation | Slide printouts |
| 13 | questionnaire | Surveys |
| 14 | resume | CVs |
| 15 | memo | Internal memos |

The AI classifies documents by **visual layout** — not by reading the text (no OCR).

---

## How the System Works (Big Picture)

```
Scanner Vendor
     |
     | drops TIFF images via SFTP
     v
[SFTP Server] ──> [sftp-ingest worker] ──> [MinIO blob storage]
                                                    |
                                                    | enqueues job via Redis
                                                    v
                                          [inference worker]
                                                    |
                                          runs AI classifier
                                                    |
                                          writes prediction to Postgres
                                                    |
                                          writes overlay image to MinIO
                                                    |
                        [FastAPI HTTP API] <── authenticated users browse results
```

**In plain English:**
1. A scanner vendor drops a document image into an SFTP folder.
2. A background watcher notices the new file within 5 seconds.
3. The file is saved to MinIO (like Amazon S3, but self-hosted).
4. A job is queued in Redis telling the AI worker "classify this document."
5. The AI worker loads the image, runs it through a neural network, and writes the predicted class + confidence score to the database.
6. It also draws an annotated overlay image showing the result.
7. Authenticated users can then call the API to browse batches and predictions.

---

## Project Phases (Build Order)

| Phase | Folder | What It Covers |
|-------|--------|----------------|
| 1 | `app/classifier/` | Train the AI model on Google Colab |
| 2 | `app/db/` | Database schema and migrations |
| 3 | `app/domain/` | Data shapes (Pydantic models) |
| 4 | `app/repositories/` | How data is read/written to the DB |
| 5 | `app/services/` | Business rules and orchestration |
| 6 | `app/api/` | HTTP endpoints users call |
| 7 | `app/infra/` | Connections to external services |
| 8 | `app/workers/` | Background jobs (ingest + inference) |

Each folder has its own `README.md` explaining that phase in detail.

---

## Services That Run Together

This project uses `docker-compose` to start 9 services simultaneously on your laptop:

| Service | What It Does |
|---------|-------------|
| `api` | The FastAPI web server |
| `worker` | Runs AI inference on queued documents |
| `sftp-ingest` | Watches SFTP for new files |
| `migrate` | Runs database migrations, then exits |
| `db` | PostgreSQL 16 database |
| `redis` | Message queue + cache |
| `minio` | File/blob storage (like S3) |
| `sftp` | SFTP server (simulates scanner vendor) |
| `vault` | Secret manager (stores passwords/keys) |

---

## Quick Start (After the Model Is Trained)

```bash
# 1. Clone the repo
git clone <repo-url>
cd docclassifier-week6

# 2. Copy the example environment file
cp .env.example .env

# 3. Start everything
docker-compose up

# 4. The API will be available at:
#    http://localhost:8000/docs   (interactive Swagger UI)
```

## Run With Docker

```bash
cd docclassifier-week6
cp .env.example .env
docker compose up --build
```

When the stack is up:
- API docs: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

The compose file starts PostgreSQL, Redis, the migration job, the API, and the Streamlit dashboard. The worker scaffolds are still placeholders in the codebase, so they are not started yet.

## Simple Dashboard

This branch adds a Streamlit dashboard.

```bash
cd docclassifier-week6
streamlit run streamlit_dashboard.py
```

Use the sidebar to sign in with your API account. If the API is not ready yet, the page still shows a demo layout so you can keep working on the interface.

---

## Three User Roles

| Role | What They Can Do |
|------|-----------------|
| `admin` | Invite users, change roles, view audit log |
| `reviewer` | View documents, fix low-confidence predictions |
| `auditor` | Read-only: view documents and audit log |

---

## Key Documentation Files

| File | Contents |
|------|----------|
| [ARCH.md](ARCH.md) | Detailed architecture diagrams and layer rules |
| [DECISIONS.md](DECISIONS.md) | Why we made specific technology choices |
| [RUNBOOK.md](RUNBOOK.md) | How to operate the system day-to-day |
| [SECURITY.md](SECURITY.md) | Security model and secret management |
| [COLLABORATION.md](COLLABORATION.md) | Team roles and how we split the work |
| [LICENSES.md](LICENSES.md) | Dataset and dependency licenses |

---

## Required Tools

- **Docker Desktop** — to run all services
- **Python 3.11** — for local development
- **Google Colab** — for training the AI model (free GPU)
- **Git + Git LFS** — the model weights file is ~110 MB, stored with LFS

---

## Performance Targets

| Metric | Target |
|--------|--------|
| API cached reads (p95) | < 50 ms |
| API uncached reads (p95) | < 200 ms |
| AI inference per document (p95) | < 1.0 s |
| End-to-end: SFTP drop → visible in API (p95) | < 10 s |
