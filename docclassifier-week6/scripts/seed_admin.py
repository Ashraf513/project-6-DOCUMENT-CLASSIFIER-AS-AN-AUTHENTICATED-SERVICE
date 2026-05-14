"""
Seed the first admin user.  Safe to run multiple times — skips if an admin already exists.

Usage (inside the running stack):
    docker-compose run --rm api python scripts/seed_admin.py

Environment variables (all have defaults):
    DATABASE_URL          — set automatically by docker-compose
    SEED_ADMIN_EMAIL      — default: admin@example.com
    SEED_ADMIN_PASSWORD   — default: Admin1234!
"""

import asyncio
import os
import sys
import uuid

# Ensure /app is on the path (docker-compose mounts it as WORKDIR)
sys.path.insert(0, "/app")

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.db.models import User
from app.infra.security import hash_password

EMAIL    = os.getenv("SEED_ADMIN_EMAIL",    "admin@example.com")
PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin1234!")
DB_URL   = os.environ.get("DATABASE_URL", "postgresql+asyncpg://docclassifier:docclassifier_dev@db:5432/docclassifier")


async def main() -> None:
    engine  = create_async_engine(DB_URL, echo=False)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        async with session.begin():
            result = await session.execute(
                select(func.count()).select_from(User).where(User.role == "admin")
            )
            admin_count = result.scalar_one()

            if admin_count > 0:
                print(f"[seed-admin] {admin_count} admin(s) already exist — nothing to do.")
                return

            new_user = User(
                id=str(uuid.uuid4()),
                email=EMAIL,
                hashed_password=hash_password(PASSWORD),
                role="admin",
                is_active=True,
            )
            session.add(new_user)

    print(f"[seed-admin] Admin created successfully.")
    print(f"             Email   : {EMAIL}")
    print(f"             Password: {PASSWORD}")
    print(f"             → Login at http://localhost:8000/docs")

    await engine.dispose()


asyncio.run(main())
