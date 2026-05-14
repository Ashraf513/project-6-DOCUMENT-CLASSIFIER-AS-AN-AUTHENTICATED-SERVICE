# File: app/api/main.py

import os
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

from app.api.routers import auth, users, batches, predictions
from app.infra.vault import get_secret
from app.classifier.model import verify_model_integrity


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Verify classifier before startup
    verify_model_integrity()

    # Validate Vault access
    jwt_secret = get_secret("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("JWT secret missing from Vault")

    # Initialize Redis cache
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=True)

    FastAPICache.init(
        RedisBackend(redis_client),
        prefix="doc-classifier-cache",
    )

    yield

    await redis_client.close()


app = FastAPI(
    title="Document Classifier API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(batches.router)
app.include_router(predictions.router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "document-classifier-api",
    }