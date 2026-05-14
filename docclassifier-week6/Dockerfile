# syntax=docker/dockerfile:1.7
# =============================================================================
# Document Classifier — Multi-stage Dockerfile
#
# Named targets (referenced by docker-compose services):
#   api          FastAPI application  — no ML framework, ~250 MB
#   worker       Inference worker     — CPU-only torch, ~900 MB
#   sftp-ingest  SFTP file watcher   — no ML framework, ~250 MB
#   migrate      Alembic one-shot     — no ML framework, ~250 MB
#
# Build examples:
#   docker build --target api         -t docclassifier-api         .
#   docker build --target worker      -t docclassifier-worker      .
#   docker build --target sftp-ingest -t docclassifier-sftp-ingest .
#   docker build --target migrate     -t docclassifier-migrate     .
# =============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 0 · uv binary donor
#   Pin the minor version; patch updates are pulled automatically by the tag.
#   Keeping uv in its own stage lets every other stage get the binary with a
#   single COPY --from=uv line and never pays a network hit again in cache.
# ─────────────────────────────────────────────────────────────────────────────
FROM ghcr.io/astral-sh/uv:0.5 AS uv


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 · system-base
#   Minimal Debian bookworm with the OS-level runtime libs shared by all final
#   images.  Build tools (gcc, libpq-dev) deliberately excluded here — they go
#   only into builder-base so they never reach production layers.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS system-base

# Python runtime hygiene
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

# libpq5   — psycopg2-binary runtime dep (Casbin SQLAlchemy adapter)
# curl     — used only by the HEALTHCHECK instruction in the api stage
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 · builder-base
#   Adds uv and the C compiler toolchain on top of system-base.
#   gcc + libpq-dev compile psycopg2-binary and any other C extensions.
#   This stage is never used as a final image — only as a build intermediary.
# ─────────────────────────────────────────────────────────────────────────────
FROM system-base AS builder-base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv

# UV_COMPILE_BYTECODE  — pre-compile .pyc at install time → faster cold starts
# UV_LINK_MODE=copy    — CRITICAL for multi-stage: hardlinks/symlinks don't
#                        survive COPY --from; "copy" ensures real file copies
# UV_NO_CACHE          — no uv cache dir inside the build layer (saves space)
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 · deps-api
#   Installs all application dependencies EXCEPT torch/torchvision.
#   The API never runs inference (per project brief).
#
#   Layer order discipline:
#     1. Copy lock/manifest files ONLY  → cache busted only on dep changes
#     2. Install deps
#     3. Source code added by the final stage → cache stays hot during dev
# ─────────────────────────────────────────────────────────────────────────────
FROM builder-base AS deps-api

WORKDIR /build

# Only the dependency manifests — no source code yet
COPY pyproject.toml uv.lock ./

RUN uv venv /app/.venv \
    && uv sync \
        --frozen \
        --no-dev \
        --no-install-project \
        --python /app/.venv/bin/python


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 · deps-worker
#   Inherits the full API venv then adds CPU-only PyTorch on top.
#   Using a separate stage means the api image never touches these packages.
#
#   CPU-only wheels (~700 MB) vs CUDA wheels (~2 GB).
#   The brief requires inference p95 < 1.0 s on CPU with ConvNeXt Tiny/Small,
#   so CUDA is not needed.
# ─────────────────────────────────────────────────────────────────────────────
FROM deps-api AS deps-worker

# Install CPU-only torch into the pre-built venv.
# Using the venv's pip (not uv pip) to avoid lockfile coupling — torch is not
# in pyproject.toml because training happens on Colab, not in this stack.
RUN /app/.venv/bin/pip install --no-cache-dir \
        "torch>=2.4,<3" \
        "torchvision>=0.19,<1" \
        --index-url https://download.pytorch.org/whl/cpu


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 5 · api  [final]
#   Production FastAPI image.  No build tools, no torch, non-root user.
# ─────────────────────────────────────────────────────────────────────────────
FROM system-base AS api

ARG UID=1001
ARG GID=1001

# Dedicated non-root user — restricts blast radius of any container escape
RUN groupadd --gid "${GID}" appgroup \
    && useradd \
        --uid "${UID}" \
        --gid appgroup \
        --no-create-home \
        --shell /sbin/nologin \
        appuser

WORKDIR /app

# Bring in the pre-built venv (no build tools needed at runtime)
COPY --from=deps-api --chown=appuser:appgroup /app/.venv /app/.venv

# Application source — intentionally last so source edits don't bust the venv layer
COPY --chown=appuser:appgroup app/        ./app/
COPY --chown=appuser:appgroup casbin/     ./casbin/
COPY --chown=appuser:appgroup alembic/    ./alembic/
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup scripts/    ./scripts/

# Activate the venv for all subsequent commands and the running container
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

USER appuser

EXPOSE 8000

# Fails fast if the /health endpoint is unreachable; start-period gives
# lifespan (Vault + Casbin) time to complete before the first probe.
HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=20s \
    --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Exec form — PID 1 is uvicorn, so SIGTERM reaches it directly.
# --workers 1 is correct for async SQLAlchemy (each process owns its pool).
# Scale horizontally via docker-compose replicas, not --workers.
CMD ["uvicorn", "app.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 6 · worker  [final]
#   Inference worker.  Includes torch + model weights baked in.
#   Weights are stored in the repo via git LFS at:
#     app/classifier/models/classifier.pt  (~110 MB ConvNeXt Tiny)
# ─────────────────────────────────────────────────────────────────────────────
FROM system-base AS worker

ARG UID=1001
ARG GID=1001

RUN groupadd --gid "${GID}" appgroup \
    && useradd \
        --uid "${UID}" \
        --gid appgroup \
        --no-create-home \
        --shell /sbin/nologin \
        appuser

WORKDIR /app

COPY --from=deps-worker --chown=appuser:appgroup /app/.venv /app/.venv

# The worker needs app/ (service layer, infra adapters) and the model weights.
# casbin/ is not required — the worker never enforces HTTP permissions.
COPY --chown=appuser:appgroup app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

USER appuser

# rq worker listens on the "default" queue.
# --with-scheduler enables RQ's built-in cron/scheduler support.
CMD ["rq", "worker", "--with-scheduler", "default"]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 7 · sftp-ingest  [final]
#   SFTP file-watcher process.  No torch — it only polls SFTP, uploads to
#   MinIO, and enqueues RQ jobs.  Shares the same slim venv as the API.
# ─────────────────────────────────────────────────────────────────────────────
FROM system-base AS sftp-ingest

ARG UID=1001
ARG GID=1001

RUN groupadd --gid "${GID}" appgroup \
    && useradd \
        --uid "${UID}" \
        --gid appgroup \
        --no-create-home \
        --shell /sbin/nologin \
        appuser

WORKDIR /app

COPY --from=deps-api --chown=appuser:appgroup /app/.venv /app/.venv

COPY --chown=appuser:appgroup app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

USER appuser

CMD ["python", "-m", "app.workers.sftp_ingest"]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 8 · migrate  [final]
#   One-shot Alembic container.  docker-compose runs this with
#   `restart: on-failure` and `depends_on: [db]`; it exits 0 on success.
#   Runs as root — acceptable for a transient init container with no exposed
#   ports or persistent state.
# ─────────────────────────────────────────────────────────────────────────────
FROM system-base AS migrate

WORKDIR /app

COPY --from=deps-api /app/.venv /app/.venv

# Alembic only needs the migration scripts and the ORM models it imports
COPY app/db/     ./app/db/
COPY app/domain/ ./app/domain/
COPY alembic/    ./alembic/
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

CMD ["alembic", "upgrade", "head"]
