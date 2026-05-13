"""
Smoke test for Phase 1 service stubs.
Run with: python test_services_skeleton.py
"""

import asyncio
from uuid import UUID

from app.domain.user import User
from app.domain.batch import Batch, BatchDetail
from app.domain.prediction import Prediction
from app.domain.errors import (
    DomainError,
    NotFound,
    PermissionDenied,
    LastAdminError,
    InvalidStateTransition,
    RelabelNotAllowed,
)

# Import via the package to verify __init__.py exports
from app.services import UserService, BatchService, PredictionService


class MockUserRepo: pass
class MockAuditRepo: pass
class MockBatchRepo: pass
class MockPredictionRepo: pass


class MockCache:
    async def delete(self, key: str):
        pass


async def main():
    mock_cache = MockCache()
    mock_user_repo = MockUserRepo()
    mock_audit_repo = MockAuditRepo()
    mock_batch_repo = MockBatchRepo()
    mock_prediction_repo = MockPredictionRepo()

    actor = User(
        id=UUID("a" * 32),
        email="admin@test.com",
        role="admin",
        is_active=True,
    )

    # ---- domain errors are importable and subclass DomainError ----
    for exc in (NotFound, PermissionDenied, LastAdminError,
                InvalidStateTransition, RelabelNotAllowed):
        assert issubclass(exc, DomainError), f"{exc.__name__} must subclass DomainError"
    print("[PASS] domain errors importable")

    # ---- UserService ----
    user_svc = UserService(user_repo=mock_user_repo, audit_repo=mock_audit_repo, cache=mock_cache)

    me = await user_svc.get_me(actor.id)
    assert isinstance(me, User)
    print("[PASS] UserService.get_me")

    fetched = await user_svc.get_by_id(actor.id)
    assert isinstance(fetched, User)
    print("[PASS] UserService.get_by_id")

    created = await user_svc.create_user("new@example.com", "pw", "reviewer", actor)
    assert isinstance(created, User) and created.role == "reviewer"
    print("[PASS] UserService.create_user")

    changed = await user_svc.change_role(actor.id, "reviewer", actor)
    assert isinstance(changed, User)
    print("[PASS] UserService.change_role")

    users = await user_svc.list_users(actor, skip=0, limit=10)
    assert isinstance(users, list) and all(isinstance(u, User) for u in users)
    print("[PASS] UserService.list_users")

    # ---- BatchService ----
    batch_svc = BatchService(batch_repo=mock_batch_repo, audit_repo=mock_audit_repo, cache=mock_cache)

    new_batch = await batch_svc.create_batch(actor)
    assert isinstance(new_batch, Batch)
    print("[PASS] BatchService.create_batch")

    detail = await batch_svc.get_batch(new_batch.id)
    assert isinstance(detail, BatchDetail)
    print("[PASS] BatchService.get_batch")

    batch_list = await batch_svc.list_batches()
    assert isinstance(batch_list, list) and all(isinstance(b, Batch) for b in batch_list)
    print("[PASS] BatchService.list_batches")

    proc = await batch_svc.mark_processing(new_batch.id)
    assert isinstance(proc, Batch) and proc.status == "processing"
    print("[PASS] BatchService.mark_processing")

    done = await batch_svc.mark_done(new_batch.id)
    assert isinstance(done, Batch) and done.status == "done"
    print("[PASS] BatchService.mark_done")

    # ---- PredictionService ----
    pred_svc = PredictionService(prediction_repo=mock_prediction_repo, audit_repo=mock_audit_repo, cache=mock_cache)

    saved = await pred_svc.save_prediction(
        batch_id=new_batch.id,
        filename="doc.tiff",
        blob_key="uploads/doc.tiff",
        overlay_key="overlays/doc.png",
        predicted_class=3,
        confidence=0.85,
    )
    assert isinstance(saved, Prediction)
    print("[PASS] PredictionService.save_prediction")

    one = await pred_svc.get_by_id(saved.id)
    assert isinstance(one, Prediction)
    print("[PASS] PredictionService.get_by_id")

    preds = await pred_svc.get_predictions_for_batch(new_batch.id)
    assert isinstance(preds, list) and all(isinstance(p, Prediction) for p in preds)
    print("[PASS] PredictionService.get_predictions_for_batch")

    recent = await pred_svc.get_recent_predictions(5)
    assert isinstance(recent, list) and all(isinstance(p, Prediction) for p in recent)
    # recent must not be the same set as a specific batch's predictions
    assert {p.id for p in recent}.isdisjoint({p.id for p in preds}), \
        "get_recent_predictions must not delegate to get_predictions_for_batch"
    print("[PASS] PredictionService.get_recent_predictions (independent)")

    relabeled = await pred_svc.relabel(saved.id, 5, actor)
    assert isinstance(relabeled, Prediction) and relabeled.predicted_class == 5
    print("[PASS] PredictionService.relabel")

    print("\nAll smoke tests passed. Service skeleton is ready for Phase 2.")


if __name__ == "__main__":
    asyncio.run(main())
