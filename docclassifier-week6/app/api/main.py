# File: app/api/main.py

import asyncio
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import casbin
import redis.asyncio as redis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from app.api.routers import auth, users, batches, predictions, audit, upload
from app.classifier.model import verify_model_integrity
from app.infra.vault import get_secret


# ---------------------------------------------------------------------------
# Casbin SQLAlchemy adapter initialisation (runs in a thread — sync library)
# ---------------------------------------------------------------------------

async def _init_casbin_enforcer(model_path: str, policy_csv: str) -> casbin.Enforcer:
    """Load Casbin policies from DB (SQLAlchemy adapter); seed from CSV on first boot."""
    # In DEV_MODE, use SQLite file for Casbin (avoids requiring PostgreSQL)
    if os.getenv("DEV_MODE") == "1":
        sync_url = "sqlite:///casbin_dev.db"
    else:
        db_url = os.environ["DATABASE_URL"]
        sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    def _create() -> casbin.Enforcer:
        from casbin_sqlalchemy_adapter import Adapter
        adapter  = Adapter(sync_url)
        enforcer = casbin.Enforcer(model_path, adapter)

        if not enforcer.get_policy():
            with open(policy_csv) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if parts[0] == "p":
                        enforcer.add_policy(*parts[1:])
            enforcer.save_policy()
        return enforcer

    return await asyncio.to_thread(_create)


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Classifier weights: SHA-256 and top-1 threshold
    verify_model_integrity()

    # 2. JWT secret — from Vault or DEV_MODE env fallback
    jwt_secret = get_secret("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET missing (set in Vault or via DEV_MODE env)")
    # Store on app state for later use (optional)
    app.state.jwt_secret = jwt_secret

    # 3. Casbin policy file check
    policy_path = "casbin/policy.csv"
    if not os.path.exists(policy_path) or os.path.getsize(policy_path) == 0:
        raise RuntimeError("Casbin policy file is empty or missing")

    # 4. Casbin enforcer (uses SQLite in DEV_MODE)
    app.state.enforcer = await _init_casbin_enforcer("casbin/model.conf", policy_path)

    # 5. Redis client (required for cache + RQ). In DEV_MODE, allow failure if Redis not running?
    # We'll still try to connect; if it fails and DEV_MODE=1, we skip cache init but continue.
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    try:
        redis_client = redis.from_url(redis_url)
        app.state.redis = redis_client
        FastAPICache.init(RedisBackend(redis_client), prefix="")
    except Exception as exc:
        if os.getenv("DEV_MODE") == "1":
            import warnings
            warnings.warn(f"Redis unavailable — cache disabled: {exc}")
            app.state.redis = None
        else:
            raise

    yield

    # Cleanup
    if hasattr(app.state, "redis") and app.state.redis is not None:
        await app.state.redis.aclose()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Document Classifier API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — explicit origins required when credentials=True (wildcard + credentials is invalid)
_allowed_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(batches.router)
app.include_router(predictions.router)
app.include_router(audit.router)
app.include_router(upload.router)


# ---------------------------------------------------------------------------
# Login rate limiter — 5 attempts / 60 s / IP  (avoids adding slowapi dep)
# ---------------------------------------------------------------------------

_login_store: dict[str, list[float]] = defaultdict(list)
_LOGIN_MAX  = 5
_LOGIN_WIN  = 60  # seconds


@app.middleware("http")
async def login_rate_limit(request: Request, call_next):
    if request.url.path == "/auth/jwt/login":
        ip  = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = [t for t in _login_store[ip] if now - t < _LOGIN_WIN]
        _login_store[ip] = recent
        if len(recent) >= _LOGIN_MAX:
            return Response(
                content=b'{"detail":"Too many login attempts. Try again later."}',
                status_code=429,
                media_type="application/json",
            )
        _login_store[ip].append(now)
    return await call_next(request)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "document-classifier-api"}