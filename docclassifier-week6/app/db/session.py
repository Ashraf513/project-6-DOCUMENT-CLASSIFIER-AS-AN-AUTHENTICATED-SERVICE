from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/docclassifier"
)

engine = create_async_engine(DATABASE_URL, echo=False)

# autobegin=False → no implicit transaction; services control transactions explicitly
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autobegin=False
)

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session