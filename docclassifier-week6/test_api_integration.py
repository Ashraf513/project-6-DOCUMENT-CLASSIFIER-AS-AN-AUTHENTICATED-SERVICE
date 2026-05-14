"""
Full API integration test.

Prerequisites:
- docker-compose up -d  (or manual services)
- alembic upgrade head
- API running on localhost:8000, Redis on localhost:6379, DB on localhost:5432

This test:
- Creates an admin user directly in DB (bypass API).
- Logs in as admin and obtains JWT.
- Creates reviewer and auditor users via admin endpoint.
- Tests role‑based access (Casbin).
- Tests cache population and invalidation.
- Tests audit log endpoint.
"""

import asyncio
import os

import httpx
import redis.asyncio as redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.db.models import Base, User as UserORM, AuditLog as AuditLogORM
from app.repositories.user_repo import UserRepo
from app.domain.user import UserCreate, Role

BASE_URL = "http://localhost:8000"
REDIS_URL = "redis://localhost:6379/0"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/docclassifier",
)

ADMIN_EMAIL = "admin-test@example.com"
ADMIN_PASSWORD = "adminpass123"
REVIEWER_EMAIL = "reviewer-test@example.com"
REVIEWER_PASSWORD = "reviewerpass123"
AUDITOR_EMAIL = "auditor-test@example.com"
AUDITOR_PASSWORD = "auditorpass123"


async def flush_redis():
    r = redis.from_url(REDIS_URL)
    await r.flushdb()
    await r.aclose()


async def cleanup_test_users():
    """Delete reviewer and auditor rows left over from previous runs."""
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autobegin=False)
    async with async_session() as db:
        async with db.begin():
            await db.execute(
                delete(AuditLogORM)
            )
            await db.execute(
                delete(UserORM).where(
                    UserORM.email.in_([REVIEWER_EMAIL, AUDITOR_EMAIL])
                )
            )
    await engine.dispose()


async def create_admin_directly():
    """Insert an admin user into the database directly."""
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autobegin=False)
    async with async_session() as db:
        async with db.begin():
            repo = UserRepo(db)
            # Check if admin already exists
            existing = await repo.get_by_email(ADMIN_EMAIL)
            if existing:
                return
            # Repo expects an already-hashed password (the service is the
            # one place that normally calls hash_password).  We mirror that
            # contract here since we are bypassing the service.
            from app.infra.security import hash_password
            admin_data = UserCreate(
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                role=Role.admin,
            )
            await repo.create(admin_data)
        # commit is done by context manager
    await engine.dispose()


async def register_and_login(client: httpx.AsyncClient, email: str, password: str) -> str:
    """Register a user via public endpoint (role not specified, will be auditor).
    Then login and return JWT."""
    # Register
    resp = await client.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )
    # Ignore if user already exists (400/409)
    # Login
    resp = await client.post(
        f"{BASE_URL}/auth/jwt/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


async def main():
    await flush_redis()
    await cleanup_test_users()
    await create_admin_directly()

    async with httpx.AsyncClient() as client:

        # 1. Login as admin
        resp = await client.post(
            f"{BASE_URL}/auth/jwt/login",
            data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        assert resp.status_code == 200, f"Admin login failed: {resp.text}"
        admin_token = resp.json()["access_token"]
        print("✅ Admin logged in")

        # 2. Admin creates reviewer and auditor via POST /users/
        headers = {"Authorization": f"Bearer {admin_token}"}
        resp = await client.post(
            f"{BASE_URL}/users/",
            json={"email": REVIEWER_EMAIL, "password": REVIEWER_PASSWORD, "role": "reviewer"},
            headers=headers,
        )
        assert resp.status_code == 200, f"Create reviewer failed: {resp.text}"
        reviewer_id = resp.json()["id"]
        print("✅ Reviewer created")

        resp = await client.post(
            f"{BASE_URL}/users/",
            json={"email": AUDITOR_EMAIL, "password": AUDITOR_PASSWORD, "role": "auditor"},
            headers=headers,
        )
        assert resp.status_code == 200, f"Create auditor failed: {resp.text}"
        auditor_id = resp.json()["id"]
        print("✅ Auditor created")

        # 3. Login reviewer and auditor (they already exist)
        reviewer_token = await register_and_login(client, REVIEWER_EMAIL, REVIEWER_PASSWORD)
        auditor_token = await register_and_login(client, AUDITOR_EMAIL, AUDITOR_PASSWORD)

        # 4. Test /me (admin)
        resp = await client.get(f"{BASE_URL}/users/me", headers=headers)
        assert resp.status_code == 200
        print("✅ GET /me works")

        # 5. Auditor cannot create user
        auditor_headers = {"Authorization": f"Bearer {auditor_token}"}
        resp = await client.post(
            f"{BASE_URL}/users/",
            json={"email": "fail@example.com", "password": "x", "role": "auditor"},
            headers=auditor_headers,
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("✅ Auditor blocked from creating user")

        # 6. Cache invalidation: change reviewer's role to auditor
        resp = await client.get(f"{BASE_URL}/users/", headers=headers)
        assert resp.status_code == 200
        # Change role
        resp = await client.patch(
            f"{BASE_URL}/users/{reviewer_id}/role",
            json={"role": "auditor"},
            headers=headers,
        )
        assert resp.status_code == 200, f"Role change failed: {resp.text}"
        print("✅ Role changed (reviewer -> auditor)")

        # Verify list updated
        resp = await client.get(f"{BASE_URL}/users/", headers=headers)
        users = resp.json()
        changed_user = next(u for u in users if u["id"] == reviewer_id)
        assert changed_user["role"] == "auditor"
        print("✅ Cache invalidated and role reflected")

        # 7. Test batches list (empty)
        resp = await client.get(f"{BASE_URL}/batches/", headers=headers)
        assert resp.status_code == 200
        print(f"✅ GET /batches returned {len(resp.json())} batches")

        # 8. Test predictions/recent (empty)
        resp = await client.get(f"{BASE_URL}/predictions/recent", headers=headers)
        assert resp.status_code == 200
        print("✅ GET /predictions/recent works")

        # 9. Relabel with nonexistent ID -> 404
        resp = await client.patch(
            f"{BASE_URL}/predictions/nonexistent/relabel",
            json={"relabeled_class": "letter"},
            headers=headers,
        )
        assert resp.status_code == 404
        print("✅ Relabel missing ID returns 404")

        # 10. Audit log
        resp = await client.get(f"{BASE_URL}/audit/", headers=headers)
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) >= 2  # at least user creation and role change
        print(f"✅ GET /audit returned {len(logs)} entries")

        # 11. Redis cache keys
        r = redis.from_url(REDIS_URL)
        keys = await r.keys("*")
        print(f"✅ Redis has {len(keys)} cache keys")
        if keys:
            print("   Sample keys:", [k.decode() for k in keys[:5]])
        await r.aclose()

        # 12. Role-based access
        resp = await client.get(f"{BASE_URL}/batches/", headers={"Authorization": f"Bearer {reviewer_token}"})
        assert resp.status_code == 200
        print("✅ Reviewer can list batches")

        resp = await client.get(f"{BASE_URL}/users/", headers={"Authorization": f"Bearer {reviewer_token}"})
        assert resp.status_code == 403
        print("✅ Reviewer blocked from listing users")

        resp = await client.get(f"{BASE_URL}/audit/", headers={"Authorization": f"Bearer {auditor_token}"})
        assert resp.status_code == 200
        print("✅ Auditor can view audit log")

        resp = await client.patch(
            f"{BASE_URL}/predictions/someid/relabel",
            json={"relabeled_class": "letter"},
            headers={"Authorization": f"Bearer {auditor_token}"},
        )
        assert resp.status_code == 403
        print("✅ Auditor blocked from relabel")

        print("\n🎉 All API integration tests passed!")


if __name__ == "__main__":
    asyncio.run(main())