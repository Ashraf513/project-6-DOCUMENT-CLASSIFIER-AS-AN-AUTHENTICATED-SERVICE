"""
Smoke test for Phase 1 service stubs.
Run with: python test_services_skeleton.py
"""

import asyncio
from datetime import datetime, timezone

from app.domain.user import User, Role, UserCreate, UserRoleUpdate
from app.domain.batch import Batch, BatchStatus, BatchCreate
from app.domain.prediction import Prediction, PredictionCreate, PredictionRelabel
from app.domain.errors import (
    DomainError,
    NotFound,
    PermissionDenied,
    LastAdminError,
    InvalidStateTransition,
    RelabelNotAllowed,
)

from app.services import UserService, BatchService, PredictionService


class MockUserRepo: pass
class MockAuditRepo: pass
class MockBatchRepo: pass
class MockPredictionRepo: pass


class MockCache:
    async def delete(self, key: str):
        pass


async def main():
    cache = MockCache()
    user_repo = MockUserRepo()
    audit_repo = MockAuditRepo()
    batch_repo = MockBatchRepo()
    prediction_repo = MockPredictionRepo()

    actor = User(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="admin@test.com",
        role=Role.admin,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )

    # ---- domain errors ----
    for exc in (NotFound, PermissionDenied, LastAdminError,
                InvalidStateTransition, RelabelNotAllowed):
        assert issubclass(exc, DomainError), f"{exc.__name__} must subclass DomainError"
    print("[PASS] domain errors importable")

    # ---- UserService ----
    user_svc = UserService(user_repo=user_repo, audit_repo=audit_repo, cache=cache)

    me = await user_svc.get_me(actor.id)
    assert isinstance(me, User) and isinstance(me.role, Role)
    print("[PASS] UserService.get_me")

    fetched = await user_svc.get_by_id(actor.id)
    assert isinstance(fetched, User)
    print("[PASS] UserService.get_by_id")

    created = await user_svc.create_user(
        UserCreate(email="new@example.com", password="pw", role=Role.reviewer),
        actor,
    )
    assert isinstance(created, User) and created.role == Role.reviewer
    print("[PASS] UserService.create_user")

    changed = await user_svc.change_role(
        actor.id,
        UserRoleUpdate(role=Role.reviewer),
        actor,
    )
    assert isinstance(changed, User) and changed.role == Role.reviewer
    print("[PASS] UserService.change_role")

    users = await user_svc.list_users(actor, skip=0, limit=10)
    assert isinstance(users, list) and all(isinstance(u, User) for u in users)
    print("[PASS] UserService.list_users")

    # ---- BatchService ----
    batch_svc = BatchService(batch_repo=batch_repo, audit_repo=audit_repo, cache=cache)

    new_batch = await batch_svc.create_batch(BatchCreate(file_count=3), actor)
    assert isinstance(new_batch, Batch) and new_batch.status == BatchStatus.pending
    print("[PASS] BatchService.create_batch")

    summary = await batch_svc.get_batch(new_batch.id)
    assert isinstance(summary, Batch)
    print("[PASS] BatchService.get_batch")

    batch_list = await batch_svc.list_batches()
    assert isinstance(batch_list, list) and all(isinstance(b, Batch) for b in batch_list)
    print("[PASS] BatchService.list_batches")

    proc = await batch_svc.mark_processing(new_batch.id)
    assert proc.status == BatchStatus.processing
    print("[PASS] BatchService.mark_processing")

    done = await batch_svc.mark_done(new_batch.id)
    assert done.status == BatchStatus.done
    print("[PASS] BatchService.mark_done")

    failed = await batch_svc.mark_failed(new_batch.id)
    assert failed.status == BatchStatus.failed
    print("[PASS] BatchService.mark_failed")

    # ---- PredictionService ----
    pred_svc = PredictionService(prediction_repo=prediction_repo, audit_repo=audit_repo, cache=cache)

    saved = await pred_svc.save_prediction(
        PredictionCreate(
            batch_id=new_batch.id,
            filename="doc.tiff",
            blob_key="minio://documents/batches/b/original/doc.tiff",
            overlay_key="minio://documents/batches/b/overlay/doc.png",
            predicted_class="invoice",
            confidence=0.85,
        )
    )
    assert isinstance(saved, Prediction) and saved.relabeled_class is None
    print("[PASS] PredictionService.save_prediction")

    one = await pred_svc.get_by_id(saved.id)
    assert isinstance(one, Prediction)
    print("[PASS] PredictionService.get_by_id")

    preds = await pred_svc.get_predictions_for_batch(new_batch.id)
    assert isinstance(preds, list) and all(isinstance(p, Prediction) for p in preds)
    print("[PASS] PredictionService.get_predictions_for_batch")

    recent = await pred_svc.get_recent_predictions(5)
    assert isinstance(recent, list) and all(isinstance(p, Prediction) for p in recent)
    assert {p.id for p in recent}.isdisjoint({p.id for p in preds}), \
        "get_recent_predictions must not delegate to get_predictions_for_batch"
    print("[PASS] PredictionService.get_recent_predictions (independent)")

    relabeled = await pred_svc.relabel(
        saved.id,
        PredictionRelabel(relabeled_class="resume"),
        actor,
    )
    assert isinstance(relabeled, Prediction)
    assert relabeled.relabeled_class == "resume"
    assert relabeled.predicted_class != "resume", \
        "relabel must preserve the original predicted_class"
    print("[PASS] PredictionService.relabel (original predicted_class preserved)")

    # PredictionRelabel must reject unknown classes
    try:
        PredictionRelabel(relabeled_class="not_a_real_class")
    except ValueError:
        print("[PASS] PredictionRelabel rejects unknown classes")
    else:
        raise AssertionError("PredictionRelabel should have rejected an unknown class")

    print("\nAll smoke tests passed. Service skeleton is ready for Phase 2.")


if __name__ == "__main__":
    asyncio.run(main())
