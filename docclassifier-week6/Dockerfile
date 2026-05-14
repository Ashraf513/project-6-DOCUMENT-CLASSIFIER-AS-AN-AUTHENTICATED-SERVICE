# =============================================================================
# Multi‑stage Dockerfile
#
# Targets:
#   migrate      – run alembic upgrade head and exit
#   api          – FastAPI server
#   worker       – RQ inference worker
#   sftp-ingest  – SFTP poller + enqueuer
#
# Build (one target at a time):
#   docker build --target api -t docclassifier-api .
#   docker build --target worker -t docclassifier-worker .
#   …
#
# Compose uses the same file with different --target values.
# =============================================================================

# ---------------------------------------------------------------------------
# 1. Base stage — Python + all dependencies
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

# System libraries required to build psycopg2 / asyncpg from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the dependency manifest (layer cache friendly)
COPY pyproject.toml uv.lock* ./

# Install all project dependencies (including torch)
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Make sure the virtual environment is on PATH for convenience
ENV PATH="/app/.venv/bin:$PATH"

# ---------------------------------------------------------------------------
# 2. migrate — apply DB migrations
# ---------------------------------------------------------------------------
FROM base AS migrate
ENTRYPOINT ["alembic", "upgrade", "head"]

# ---------------------------------------------------------------------------
# 3. api — FastAPI server
# ---------------------------------------------------------------------------
FROM base AS api
EXPOSE 8000
# Healthcheck is used by docker-compose depends_on condition
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1
ENTRYPOINT ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# 4. worker — RQ inference worker (sync process, runs classify jobs)
# ---------------------------------------------------------------------------
FROM base AS worker
ENTRYPOINT ["rq", "worker", "--with-scheduler", "default"]

# ---------------------------------------------------------------------------
# 5. sftp-ingest — SFTP watcher + enqueuer
# ---------------------------------------------------------------------------
FROM base AS sftp-ingest
ENTRYPOINT ["python", "-m", "app.workers.sftp_ingest"]

# ---------------------------------------------------------------------------
# 6. dashboard — Streamlit UI
# ---------------------------------------------------------------------------
FROM base AS dashboard
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8501/_stcore/health || exit 1
ENTRYPOINT ["streamlit", "run", "streamlit-dashboard.py", \
            "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]