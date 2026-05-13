"""
Integration test for the service layer.

Runs against a real PostgreSQL database (empty).
Creates all tables, then exercises:
  - UserService (CRUD, permissions, audit, cache)
  - BatchService (lifecycle, audit, cache)
  - PredictionService (create, relabel, permissions, audit, cache)

Usage:
  1. Start a PostgreSQL instance.
  2. Set DATABASE_URL (or modify the script).
  3. Run: python test_services_integration.py

The test leaves the database in its final state; drop the database
afterwards if you need a clean slate.
"""

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.db.models import Base
from app.domain.user import User, Role, UserCreate, UserRoleUpdate
from app.domain.batch import Batch, BatchStatus, BatchCreate
from app.domain.prediction import Prediction, PredictionCreate, PredictionRelabel
from app.repositories.user_repo import UserRepo
from app.repositories.batch_repo import BatchRepo
from app.repositories.prediction_repo import PredictionRepo
from app.repositories.audit_repo import AuditRepo
from app.services.user_service import UserService
from app.services.batch_service import BatchService
from app.services.prediction_service import PredictionService
from app.infra.cache import (
    InMemoryCacheInvalidator,
    USERS_LIST_KEY,
    BATCHES_LIST_KEY,
    PREDICTIONS_RECENT_KEY,
    batch_key,
    predictions_batch_key,
    user_me_key,
)
from app.services.exceptions import (
    PermissionDenied,
    NotFound,
    LastAdminError,
    RelabelNotAllowed,
    InvalidStateTransition,
)

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/docclassifier_test"
)

engine = create_async_engine(DATABASE_URL, echo=False)   # echo=True to see SQL
TestSession = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autobegin=False
)


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# The actual test
# ---------------------------------------------------------------------------
async def main():
    # 1. Fresh schema
    await drop_tables()
    await create_tables()
    print("✅ Tables created")

    # 2. Shared cache (in‑memory) – services will record invalidations here
    cache = InMemoryCacheInvalidator()

    # 3. Create the first admin user and a reviewer user via repo
    #    (bypasses services so we have valid actors for tests)
    admin_data = UserCreate(
        email="admin@example.com",
        password="hashed_admin_password",
        role=Role.admin,
    )
    reviewer_data = UserCreate(
        email="reviewer@example.com",
        password="hashed_reviewer_password",
        role=Role.reviewer,
    )

    async with TestSession() as db:
        async with db.begin():
            admin_user_orm = await UserRepo(db).create(admin_data)
            reviewer_user_orm = await UserRepo(db).create(reviewer_data)
        admin = User.model_validate(admin_user_orm)
        new_user = User.model_validate(reviewer_user_orm)

    print(f"🔧 Admin user created: {admin.email} id={admin.id}")
    print(f"🔧 Reviewer user created: {new_user.email} id={new_user.id}")

    # =====================================================================
    # USER SERVICE TESTS
    # =====================================================================
    async with TestSession() as session:
        user_svc = UserService(session, cache)

        # --- get_me ---
        me = await user_svc.get_me(admin.id)
        assert me.email == admin.email, "get_me returned wrong user"
        print("✅ get_me works")

        # --- get_by_id (same as get_me) ---
        same = await user_svc.get_by_id(admin.id)
        assert same.email == admin.email
        print("✅ get_by_id works")

        # --- create_user (admin) ---
        new_user_data = UserCreate(
            email="extra@example.com",
            password="plain_text_will_be_hashed",
            role=Role.reviewer,
        )
        extra_user = await user_svc.create_user(new_user_data, actor=admin)
        assert extra_user.email == "extra@example.com"
        assert extra_user.role == Role.reviewer
        print("✅ create_user (admin) works, password hashed")

        # --- create_user (non‑admin) ---
        try:
            await user_svc.create_user(
                UserCreate(email="fail@example.com", password="x", role=Role.auditor),
                actor=new_user,   # reviewer is not admin
            )
            assert False, "Should have raised PermissionDenied"
        except PermissionDenied:
            print("✅ create_user rejected non‑admin")

        # --- change_role (admin) ---
        # Change the reviewer's role to auditor
        updated = await user_svc.change_role(
            new_user.id,
            UserRoleUpdate(role=Role.auditor),
            actor=admin,
        )
        assert updated.role == Role.auditor
        new_user = updated  # update variable
        print("✅ change_role works")

        # --- last‑admin check ---
        # We have only one admin (admin). Try to demote them.
        try:
            await user_svc.change_role(
                admin.id,
                UserRoleUpdate(role=Role.reviewer),
                actor=admin,
            )
            assert False, "Should have raised LastAdminError"
        except LastAdminError:
            print("✅ Last admin cannot be demoted")

        # --- list_users (admin) ---
        all_users = await user_svc.list_users(actor=admin)
        assert len(all_users) >= 2
        print(f"✅ list_users returned {len(all_users)} users")

        # --- list_users (non‑admin) ---
        try:
            await user_svc.list_users(actor=new_user)   # now auditor
            assert False, "Should have raised PermissionDenied"
        except PermissionDenied:
            print("✅ list_users rejected non‑admin")

    # Check cache invalidations after user operations
    assert f"user:me:{new_user.id}" in cache.deleted, "user:me key for changed user not invalidated"
    assert USERS_LIST_KEY in cache.deleted, "users list cache not invalidated"
    print("✅ User caches invalidated correctly")

    # =====================================================================
    # BATCH SERVICE TESTS
    # =====================================================================
    async with TestSession() as session:
        batch_svc = BatchService(session, cache)

        # --- create_batch ---
        batch = await batch_svc.create_batch(actor=admin)
        assert batch.status == BatchStatus.pending
        assert batch.file_count == 0
        print("✅ create_batch works")

        # --- get_batch ---
        fetched = await batch_svc.get_batch(batch.id)
        assert fetched.id == batch.id
        print("✅ get_batch works")

        # --- list_batches ---
        batches = await batch_svc.list_batches()
        assert len(batches) >= 1
        print(f"✅ list_batches returned {len(batches)} batches")

        # --- mark_processing ---
        proc = await batch_svc.mark_processing(batch.id)
        assert proc.status == BatchStatus.processing
        print("✅ mark_processing works")

        # --- mark_done from processing ---
        done = await batch_svc.mark_done(batch.id)
        assert done.status == BatchStatus.done
        print("✅ mark_done works")

        # --- invalid transition (done -> processing) ---
        try:
            await batch_svc.mark_processing(batch.id)
            assert False, "Should have raised InvalidStateTransition"
        except InvalidStateTransition:
            print("✅ Invalid state transition rejected")

        # --- mark_failed from pending ---
        new_batch = await batch_svc.create_batch()
        failed = await batch_svc.mark_failed(new_batch.id)
        assert failed.status == BatchStatus.failed
        print("✅ mark_failed from pending works")

    # Cache invalidation for batches
    assert BATCHES_LIST_KEY in cache.deleted
    print("✅ Batch caches invalidated correctly")

    # =====================================================================
    # PREDICTION SERVICE TESTS
    # =====================================================================
    async with TestSession() as session:
        pred_svc = PredictionService(session, cache)

        # First create a fresh batch
        batch_svc = BatchService(session, cache)
        batch = await batch_svc.create_batch()

        # --- save_prediction ---
        pred_data = PredictionCreate(
            batch_id=batch.id,
            filename="doc1.tiff",
            blob_key="minio://documents/batches/b1/original/doc1.tiff",
            overlay_key="minio://documents/batches/b1/overlay/doc1.png",
            predicted_class="invoice",
            confidence=0.85,
        )
        pred = await pred_svc.save_prediction(batch.id, pred_data)
        assert pred.predicted_class == "invoice"
        assert pred.confidence == 0.85
        print("✅ save_prediction works")

        # --- get_by_id ---
        fetched_pred = await pred_svc.get_by_id(pred.id)
        assert fetched_pred.id == pred.id
        print("✅ get_by_id works")

        # --- get_predictions_for_batch ---
        preds = await pred_svc.get_predictions_for_batch(batch.id)
        assert len(preds) == 1
        print("✅ get_predictions_for_batch works")

        # --- get_recent_predictions ---
        recent = await pred_svc.get_recent_predictions(limit=5)
        assert any(p.id == pred.id for p in recent)
        print("✅ get_recent_predictions works")

        # --- relabel (admin) ---
        relabeled = await pred_svc.relabel(
            pred.id,
            PredictionRelabel(relabeled_class="resume"),
            actor=admin,
        )
        assert relabeled.relabeled_class == "resume"
        print("✅ relabel by admin works")

        # --- relabel (non‑reviewer: auditor) ---
        try:
            await pred_svc.relabel(
                pred.id,
                PredictionRelabel(relabeled_class="invoice"),
                actor=new_user,   # still auditor
            )
            assert False, "Should have raised PermissionDenied"
        except PermissionDenied:
            print("✅ Relabel rejected for non‑reviewer (auditor)")

        # Make new_user a reviewer again for next tests
        async def make_reviewer(session, user_id):
            async with session.begin():
                await UserRepo(session).update_role(user_id, Role.reviewer)

        await make_reviewer(session, new_user.id)
        new_user = new_user.model_copy(update={"role": Role.reviewer})

        # --- relabel (reviewer on high confidence) ---
        high_conf_pred = await pred_svc.save_prediction(
            batch.id,
            PredictionCreate(
                batch_id=batch.id,
                filename="doc2.tiff",
                blob_key="minio://x",
                overlay_key="minio://y",
                predicted_class="form",
                confidence=0.95,
            ),
        )
        try:
            await pred_svc.relabel(
                high_conf_pred.id,
                PredictionRelabel(relabeled_class="invoice"),
                actor=new_user,
            )
            assert False, "Should have raised RelabelNotAllowed"
        except RelabelNotAllowed:
            print("✅ Reviewer cannot relabel high‑confidence prediction")

        # --- reviewer relabel of low‑confidence ---
        low_conf_pred = await pred_svc.save_prediction(
            batch.id,
            PredictionCreate(
                batch_id=batch.id,
                filename="doc3.tiff",
                blob_key="minio://z",
                overlay_key="minio://w",
                predicted_class="email",
                confidence=0.35,
            ),
        )
        relabeled_by_reviewer = await pred_svc.relabel(
            low_conf_pred.id,
            PredictionRelabel(relabeled_class="letter"),
            actor=new_user,
        )
        assert relabeled_by_reviewer.relabeled_class == "letter"
        print("✅ Reviewer relabel of low‑confidence works")

    # Cache invalidation for predictions
    assert PREDICTIONS_RECENT_KEY in cache.deleted
    assert batch_key(batch.id) in cache.deleted
    print("✅ Prediction caches invalidated correctly")

    # =====================================================================
    # TRANSACTIONAL ROLLBACK TEST
    # =====================================================================
    async with TestSession() as session:
        user_svc = UserService(session, cache)

        # Monkey-patch audit create to throw, to test rollback
        original_audit_create = AuditRepo.create
        async def _failing_create(self, *args, **kwargs):
            raise RuntimeError("Simulated audit failure")
        AuditRepo.create = _failing_create

        try:
            await user_svc.create_user(
                UserCreate(email="should_rollback@example.com", password="pw", role=Role.auditor),
                actor=admin,
            )
            assert False, "Should have raised"
        except RuntimeError:
            pass  # expected

        # Restore
        AuditRepo.create = original_audit_create

        # Verify the user was NOT created (rolled back)
        async with TestSession() as check_session:
            async with check_session.begin():
                check_user = await UserRepo(check_session).get_by_email("should_rollback@example.com")
            assert check_user is None, "User should have been rolled back"
        print("✅ Transaction rollback works (user not persisted after audit failure)")

    # =====================================================================
    # AUDIT LOG VERIFICATION
    # =====================================================================
    async with TestSession() as session:
        async with session.begin():
            audit_repo = AuditRepo(session)
            all_logs = await audit_repo.list_recent(limit=50)
        actions = [log.action for log in all_logs]
        expected_actions = [
            "user_create", "role_change", "batch_created",
            "batch_state_change", "relabel", "user_create"
        ]
        for action in expected_actions:
            assert action in actions, f"Missing audit action: {action}"
        print("✅ Audit logs contain all expected actions")

    # =====================================================================
    # CLEANUP
    # =====================================================================
    # Uncomment the next line if you want the test to leave the DB clean.
    # await drop_tables()
    print("\n🎉 All integration tests passed!")


if __name__ == "__main__":
    asyncio.run(main())