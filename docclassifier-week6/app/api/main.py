# File: app/api/main.py

import os
from contextlib import asynccontextmanager

import casbin
import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from app.api.routers import auth, users, batches, predictions, audit
from app.classifier.model import verify_model_integrity
from app.infra.vault import get_secret

# Temporary fallback for local testing without Vault
import os as _os
_jwt = _os.getenv("JWT_SECRET")
if _jwt:
    import app.infra.vault as _vault
    _vault.get_secret = lambda key: _os.getenv(key)
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---------------------------------------------------------------
    # 1. Verify classifier weights and SHA-256 match
    # ---------------------------------------------------------------
    verify_model_integrity()

    # ---------------------------------------------------------------
    # 2. Validate Vault: JWT secret must be present
    # ---------------------------------------------------------------
    jwt_secret = get_secret("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("JWT secret missing from Vault")

    # ---------------------------------------------------------------
    # 3. Validate Casbin policy file is non‑empty
    # ---------------------------------------------------------------
    policy_path = "casbin/policy.csv"
    if not os.path.exists(policy_path) or os.path.getsize(policy_path) == 0:
        raise RuntimeError("Casbin policy file is empty or missing")

    # ---------------------------------------------------------------
    # 4. Create a single Casbin enforcer and attach to app.state
    # ---------------------------------------------------------------
    app.state.enforcer = casbin.Enforcer("casbin/model.conf", policy_path)

    # ---------------------------------------------------------------
    # 5. Initialize Redis cache (prefix empty so keys match exactly
    #    those used by RedisCacheInvalidator)
    # ---------------------------------------------------------------
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis.from_url(redis_url)
    FastAPICache.init(RedisBackend(redis_client), prefix="")
    yield
    await redis_client.close()


app = FastAPI(
    title="Document Classifier API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (adjust origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(batches.router)
app.include_router(predictions.router)
app.include_router(audit.router)   # ← new


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "document-classifier-api",
    }