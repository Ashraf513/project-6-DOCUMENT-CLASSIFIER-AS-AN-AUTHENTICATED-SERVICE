import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.db.models import Base
from app.repositories.user_repo import UserRepo

# Use async SQLite for testing
engine = create_async_engine("sqlite+aiosqlite:///:memory:")
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@pytest.mark.asyncio
async def test_user_repo():
    async with async_session_maker() as session:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        repo = UserRepo(session)
        user = await repo.create("test@test.com", "hash", "admin")
        assert user.id is not None
        fetched = await repo.get_by_id(user.id)
        assert fetched.email == "test@test.com"