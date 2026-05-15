import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.environ["DATABASE_URL"]  # must be set; no insecure default

# Async engine — used by the FastAPI app and sftp-ingest worker
engine = create_async_engine(DATABASE_URL, echo=False)

# autobegin=False: no implicit transaction; services control boundaries explicitly
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autobegin=False
)

# Synchronous engine — used by RQ inference workers (sync execution context).
# Derives the psycopg2 URL by stripping the +asyncpg dialect modifier.
_sync_url = DATABASE_URL.replace("+asyncpg", "")
_sync_engine = create_engine(_sync_url, echo=False, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=_sync_engine, expire_on_commit=False)
