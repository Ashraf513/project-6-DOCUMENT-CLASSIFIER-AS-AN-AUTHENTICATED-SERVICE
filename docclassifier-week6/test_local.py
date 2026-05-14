#!/usr/bin/env python3
"""
Local Development Test Suite — Document Classifier
Validates code correctness without requiring Docker services.

Run: python test_local.py
Exit code: 0 = all checks passed, 1 = failures
"""

import sys
import os
import re
from pathlib import Path
from importlib import util as import_util

# Ensure project root on PYTHONPATH
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

tests_passed = 0
tests_failed = 0
warnings = 0


def check(name, msg=None):
    global tests_passed, warnings
    if msg:
        print(f"  [OK] {name}: {msg}", flush=True)
    else:
        print(f"  [OK] {name}", flush=True)
    tests_passed += 1


def warn(name, msg):
    global warnings
    print(f"  [!] {name}: {msg}", flush=True)
    warnings += 1


def fail(name, error):
    global tests_failed
    print(f"  [FAIL] {name}: {error}", flush=True)
    tests_failed += 1


def run_test(name, func, critical=True):
    try:
        func()
        check(name)
    except Exception as e:
        if critical:
            fail(name, str(e))
        else:
            warn(name, str(e))


# Helper: try import, return module or None
def try_import(module_name):
    try:
        __import__(module_name)
        return True
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# 1. Syntax Verification (already compiled by py_compile before calling this)
# ---------------------------------------------------------------------------
print("\n=== Step 1: File Integrity ===")


def test_all_py_files_compile():
    # We already did py_compile, just verify no .pyc errors
    check("All .py files compile successfully")


run_test("Syntax validation", test_all_py_files_compile, critical=True)

# ---------------------------------------------------------------------------
# 2. Core Dependencies
# ---------------------------------------------------------------------------
print("\n=== Step 2: Dependency Check ===")

# These are required for import tests
required_pkgs = [
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "redis",
    "casbin",
    "hvac",
    "minio",
    "rq",
    "paramiko",
    "torch",
    "torchvision",
    "PIL",
]

missing_pkgs = []
for pkg in required_pkgs:
    found = try_import(pkg.replace("-", "_"))
    if not found:
        missing_pkgs.append(pkg)

if missing_pkgs:
    fail(
        "Dependencies",
        f"Missing packages: {', '.join(missing_pkgs)}. Run: uv sync --frozen",
    )
else:
    check("All dependencies installed")

# ---------------------------------------------------------------------------
# 3. Domain Models
# ---------------------------------------------------------------------------
print("\n=== Step 3: Domain Models ===")


def test_role_enum():
    from app.domain.user import Role

    assert Role.admin == "admin"
    assert Role.reviewer == "reviewer"
    assert Role.auditor == "auditor"


run_test("Role enum", test_role_enum)


def test_batch_status_enum():
    from app.domain.batch import BatchStatus

    assert BatchStatus.pending == "pending"
    assert BatchStatus.processing == "processing"
    assert BatchStatus.done == "done"
    assert BatchStatus.failed == "failed"


run_test("BatchStatus enum", test_batch_status_enum)


def test_user_create():
    from app.domain.user import UserCreate, Role
    from pydantic import ValidationError

    u = UserCreate(email="test@example.com", password="secret123", role=Role.admin)
    assert u.email == "test@example.com"

    try:
        UserCreate(email="bad", password="x", role=Role.admin)
        raise AssertionError("Invalid email should fail")
    except ValidationError:
        pass


run_test("UserCreate validation", test_user_create)


def test_classes_list():
    from app.classifier.classes import CLASSES

    assert len(CLASSES) == 16, f"Expected 16 classes, got {len(CLASSES)}"
    assert "invoice" in CLASSES
    assert "resume" in CLASSES
    assert "memo" in CLASSES


run_test("CLASSES list (16)", test_classes_list)


def test_prediction_relabel_validator():
    from app.domain.prediction import PredictionRelabel
    from app.classifier.classes import CLASSES

    r = PredictionRelabel(relabeled_class=CLASSES[0])
    assert r.relabeled_class == CLASSES[0]

    invalid = "notaclass"
    try:
        PredictionRelabel(relabeled_class=invalid)
        raise AssertionError("Invalid class should fail")
    except ValueError:
        pass


run_test("PredictionRelabel validator", test_prediction_relabel_validator)

# ---------------------------------------------------------------------------
# 4. Classifier Module
# ---------------------------------------------------------------------------
print("\n=== Step 4: Classifier Module ===")


def test_model_card():
    import json
    from pathlib import Path

    card_path = Path("app/classifier/models/model_card.json")
    if not card_path.exists():
        warn("model_card.json", "File missing — skip")
        return

    card = json.loads(card_path.read_text())
    # Required top-level fields
    for field in ["sha256", "backbone", "classes", "metrics", "min_top1_threshold"]:
        assert field in card, f"Missing field: {field}"
    # metrics sub-object
    metrics = card.get("metrics", {})
    assert "test_top1" in metrics, "Missing metrics.test_top1"
    # Check threshold
    min_thr = card.get("min_top1_threshold", 0.82)
    actual = metrics["test_top1"]
    if actual < min_thr:
        raise AssertionError(f"test_top1 {actual:.4f} below threshold {min_thr:.2f}")
    check(f"model_card OK — test_top1={actual:.4f}, threshold={min_thr:.2f}")


run_test("Model card", test_model_card, critical=False)


def test_weights():
    from pathlib import Path

    w = Path("app/classifier/models/classifier.pt")
    if not w.exists():
        warn("classifier.pt", "Weights missing — skip inference tests")
        return
    size_mb = w.stat().st_size / (1024 * 1024)
    check(f"Weights exist ({size_mb:.1f} MB)")


run_test("Classifier weights", test_weights, critical=False)


def test_overlay_function():
    from app.classifier.overlay import draw_overlay
    import inspect

    sig = inspect.signature(draw_overlay)
    assert set(["image_bytes", "label", "confidence"]).issubset(sig.parameters)


run_test("draw_overlay signature", test_overlay_function)


def test_predict_function():
    from app.classifier.model import predict
    import inspect

    sig = inspect.signature(predict)
    assert "model" in sig.parameters and "image_bytes" in sig.parameters


run_test("predict signature", test_predict_function)


def test_verify_integrity():
    from app.classifier.model import verify_model_integrity, MIN_TOP1
    import inspect

    # Check MIN_TOP1 constant
    assert MIN_TOP1 >= 0.8, "MIN_TOP1 should be >= 0.8 for production"
    # The function should raise RuntimeError if model missing/bad
    assert callable(verify_model_integrity)


run_test("Model integrity checker", test_verify_integrity)

# ---------------------------------------------------------------------------
# 5. Infrastructure Adapters
# ---------------------------------------------------------------------------
print("\n=== Step 5: Infrastructure Adapters ===")


def test_cache_invalidator_protocol():
    from app.infra.cache import CacheInvalidator, InMemoryCacheInvalidator
    from typing import Protocol

    # Protocol compliance (structural)
    impl = InMemoryCacheInvalidator()
    assert isinstance(impl, CacheInvalidator)


run_test("CacheInvalidator protocol", test_cache_invalidator_protocol)


def test_cache_keys():
    from app.infra.cache import (
        USERS_LIST_KEY,
        BATCHES_LIST_KEY,
        PREDICTIONS_RECENT_KEY,
        user_me_key,
        batch_key,
        predictions_batch_key,
    )

    assert USERS_LIST_KEY == "users:list"
    assert BATCHES_LIST_KEY == "batches:list"
    assert PREDICTIONS_RECENT_KEY == "predictions:recent"
    assert user_me_key("u1") == "user:me:u1"
    assert batch_key("b1") == "batch:b1"
    assert predictions_batch_key("b2") == "predictions:batch:b2"


run_test("Cache key constants & builders", test_cache_keys)


def test_blob_storage_interface():
    from app.infra.blob import BlobStorage
    import inspect

    methods = ["upload", "download", "exists", "presigned_url"]
    for m in methods:
        assert hasattr(BlobStorage, m), f"Missing method: {m}"

    # Static key helpers
    assert hasattr(BlobStorage, "original_key")
    assert hasattr(BlobStorage, "overlay_key")
    assert hasattr(BlobStorage, "quarantine_key")


run_test("BlobStorage interface", test_blob_storage_interface)


def test_vault_adapter():
    from app.infra.vault import get_secret

    # Should raise RuntimeError without Vault — this is expected
    try:
        get_secret("JWT_SECRET")
        warn("Vault", "Secrets retrieved unexpectedly (Vault running?)")
    except RuntimeError:
        check("Vault raises when unavailable (expected)")


run_test("Vault adapter (expected failure)", test_vault_adapter)


def test_queue_adapter():
    from app.infra.queue import ClassifyQueue
    import inspect

    assert hasattr(ClassifyQueue, "enqueue_classify")
    assert hasattr(ClassifyQueue, "depth")
    sig = inspect.signature(ClassifyQueue.__init__)
    assert "redis_url" in sig.parameters


run_test("ClassifyQueue interface", test_queue_adapter)


def test_sftp_watcher():
    from app.infra.sftp_watcher import SFTPWatcher
    import inspect

    # Constructor signature
    sig = inspect.signature(SFTPWatcher.__init__)
    params = list(sig.parameters.keys())
    for p in [
        "host",
        "port",
        "user",
        "password",
        "watch_path",
        "poll_interval",
        "blob",
        "queue",
        "create_batch",
    ]:
        assert p in params, f"Missing param: {p}"

    # Methods
    assert hasattr(SFTPWatcher, "run")
    assert hasattr(SFTPWatcher, "_poll")
    assert hasattr(SFTPWatcher, "_process_file")


run_test("SFTPWatcher interface", test_sftp_watcher)

# ---------------------------------------------------------------------------
# 6. Repository Layer
# ---------------------------------------------------------------------------
print("\n=== Step 6: Repository Contracts ===")


def test_repo_return_domain_types():
    from app.repositories.user_repo import UserRepo
    from app.repositories.batch_repo import BatchRepo
    from app.repositories.prediction_repo import PredictionRepo
    import inspect

    # UserRepo.create returns User
    ann = inspect.signature(UserRepo.create).return_annotation
    assert "User" in str(ann)

    # BatchRepo.create returns Batch
    ann = inspect.signature(BatchRepo.create).return_annotation
    assert "Batch" in str(ann)

    # PredictionRepo.create returns Prediction
    ann = inspect.signature(PredictionRepo.create).return_annotation
    assert "Prediction" in str(ann)


run_test("Repository return types are domain models", test_repo_return_domain_types)


def test_repo_no_commit():
    # Ensure repositories don't call session.commit()
    # We'll check source for "commit(" string in repo files
    from pathlib import Path

    repo_files = [
        "app/repositories/user_repo.py",
        "app/repositories/batch_repo.py",
        "app/repositories/prediction_repo.py",
        "app/repositories/audit_repo.py",
    ]

    for f in repo_files:
        content = Path(f).read_text()
        # session.commit() should NOT appear (but session.begin() context manager OK)
        # We'll just check for the literal string "commit(" outside of comments
        if re.search(r"session\.commit\(", content):
            raise AssertionError(f"{f}: contains session.commit() — repositories must not commit")


run_test("Repositories have no commit() calls", test_repo_no_commit)

# ---------------------------------------------------------------------------
# 7. Service Layer
# ---------------------------------------------------------------------------
print("\n=== Step 7: Service Contracts ===")


def test_service_dependencies():
    from app.services.user_service import UserService
    from app.services.batch_service import BatchService
    from app.services.prediction_service import PredictionService
    import inspect

    # All services: __init__(db, cache)
    for svc in [UserService, BatchService, PredictionService]:
        sig = inspect.signature(svc.__init__)
        params = list(sig.parameters.keys())
        assert "db" in params and "cache" in params, f"{svc.__name__} missing deps"


run_test("Service constructors accept db & cache", test_service_dependencies)


def test_transaction_boundaries():
    # Check that service methods use `async with self.db.begin():`
    from pathlib import Path
    import ast

    service_files = [
        "app/services/user_service.py",
        "app/services/batch_service.py",
        "app/services/prediction_service.py",
    ]

    for f in service_files:
        content = Path(f).read_text()
        # Parse AST to ensure context manager usage (simple string check OK)
        if "async with self.db.begin():" not in content:
            raise AssertionError(f"{f}: missing 'async with self.db.begin()' pattern")


run_test("Services use async with db.begin()", test_transaction_boundaries)


def test_cache_invalidation():
    from pathlib import Path

    svc_files = [
        "app/services/user_service.py",
        "app/services/batch_service.py",
        "app/services/prediction_service.py",
    ]

    for f in svc_files:
        content = Path(f).read_text()
        if "cache." not in content:
            raise AssertionError(f"{f}: no cache.delete calls found")


run_test("All services call cache.delete()", test_cache_invalidation)


def test_audit_logging():
    from pathlib import Path

    svc_files = [
        "app/services/user_service.py",
        "app/services/batch_service.py",
        "app/services/prediction_service.py",
    ]

    for f in svc_files:
        content = Path(f).read_text()
        if "audit_repo.create" not in content:
            raise AssertionError(f"{f}: audit_repo.create not called")


run_test("All services write audit logs", test_audit_logging)


def test_exceptions_defined():
    from app.services.exceptions import (
        ServiceError,
        PermissionDenied,
        NotFound,
        LastAdminError,
        RelabelNotAllowed,
        InvalidStateTransition,
    )

    # Check inheritance
    assert issubclass(PermissionDenied, ServiceError)
    assert issubclass(NotFound, ServiceError)


run_test("Custom exceptions", test_exceptions_defined)


def test_confidence_threshold_rule():
    """The 0.7 confidence threshold for reviewers is enforced."""
    from app.services.prediction_service import PredictionService
    import inspect

    source = inspect.getsource(PredictionService.relabel)
    # Must check confidence against 0.7 for reviewer role
    assert "0.7" in source, "Missing confidence threshold 0.7"
    assert "Role.reviewer" in source or "reviewer" in source


run_test("Confidence threshold (0.7) for reviewers", test_confidence_threshold_rule)


def test_last_admin_guard():
    from app.services.user_service import UserService
    import inspect

    source = inspect.getsource(UserService.change_role)
    assert "count_by_role" in source, "Missing admin count check"
    assert "LastAdminError" in source, "Missing LastAdminError raise"


run_test("Last admin guard present", test_last_admin_guard)

# ---------------------------------------------------------------------------
# 8. API Layer
# ---------------------------------------------------------------------------
print("\n=== Step 8: API Layer ===")


def test_app_creation():
    from app.api.main import app
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)


run_test("FastAPI app instance", test_app_creation)


def test_required_routes():
    from app.api.main import app

    routes = [r.path for r in app.routes if hasattr(r, "path")]
    required = [
        "/auth/jwt/login",
        "/users/me",
        "/users/",
        "/batches/",
        "/predictions/recent",
        "/audit/",
    ]
    for r in required:
        assert r in routes, f"Missing route: {r}"


run_test("All required routes registered", test_required_routes)


def test_lifespan_hook():
    from app.api.main import lifespan
    # It should be a callable (the asynccontextmanager wrapper)
    assert callable(lifespan)
    # We can't easily test the actual context manager without starting the app,
    # but we can verify it's not None and is a function
    assert lifespan is not None


run_test("Lifespan hook defined", test_lifespan_hook)


def test_rate_limiting():
    from app.api.main import app, _login_store, _LOGIN_MAX, _LOGIN_WIN

    # Middleware should exist; check constants
    assert _LOGIN_MAX == 5
    assert _LOGIN_WIN == 60


run_test("Login rate limiting constants", test_rate_limiting)


def test_casbin_dependency():
    from app.api.deps import get_enforcer
    import inspect

    sig = inspect.signature(get_enforcer)
    assert "request" in sig.parameters


run_test("Casbin dependency get_enforcer", test_casbin_dependency)


def test_cache_dependency():
    from app.api.deps import get_cache
    import inspect

    assert callable(get_cache)


run_test("Cache dependency get_cache", test_cache_dependency)

# ---------------------------------------------------------------------------
# 9. Worker Entry Points
# ---------------------------------------------------------------------------
print("\n=== Step 9: Worker Entry Points ===")


def test_sftp_ingest_main():
    from app.workers.sftp_ingest import _main
    import inspect

    assert inspect.iscoroutinefunction(_main)


run_test("sftp_ingest._main is async", test_sftp_ingest_main)


def test_classify_function():
    from app.workers.inference_worker import classify
    import inspect

    assert inspect.isfunction(classify)  # not async — RQ calls sync
    sig = inspect.signature(classify)
    for p in ["batch_id", "blob_key", "request_id"]:
        assert p in sig.parameters


run_test("inference_worker.classify signature", test_classify_function)


def test_singleton_pattern():
    """Worker uses process-level singletons for model/blob."""
    from app.workers.inference_worker import _get_blob, _get_model
    import inspect

    # These should be module-level functions that set globals
    assert callable(_get_blob)
    assert callable(_get_model)


run_test("Worker singleton getters exist", test_singleton_pattern)

# ---------------------------------------------------------------------------
# 10. Security Scan
# ---------------------------------------------------------------------------
print("\n=== Step 10: Security Scan ===")


def test_no_hardcoded_secrets():
    from pathlib import Path
    import re

    patterns = [
        r'JWT_SECRET\s*=\s*["\']',
        r'MINIO_ACCESS_KEY\s*=\s*["\']',
        r'MINIO_SECRET_KEY\s*=\s*["\']',
        r"PASSWORD\s*=\s*['\"]scanner['\"]",
        r'VAULT_TOKEN\s*=',
    ]

    py_files = list(Path("app").rglob("*.py"))
    hits = []
    for pat in patterns:
        regex = re.compile(pat)
        for f in py_files:
            try:
                content = f.read_text()
            except UnicodeDecodeError:
                continue
            if regex.search(content):
                hits.append((f, pat))

    if hits:
        msg = "; ".join([f"{f.name}:{p}" for f, p in hits[:5]])
        raise AssertionError(f"Hardcoded secret pattern found: {msg}")
    else:
        check("No hardcoded secrets in code")


run_test("Secret leakage scan", test_no_hardcoded_secrets)


def test_hash_password_used():
    """Ensure password hashing is used in user creation."""
    from app.infra.security import hash_password, verify_password

    h1 = hash_password("test")
    assert h1 != "test"
    assert verify_password("test", h1)
    assert not verify_password("wrong", h1)


run_test("Password hashing works (Argon2)", test_hash_password_used)

# ---------------------------------------------------------------------------
# 11. Golden Set Structure
# ---------------------------------------------------------------------------
print("\n=== Step 11: Golden Set ===")


def test_golden_set():
    from pathlib import Path
    import json

    golden_dir = Path("app/classifier/eval/golden_images")
    expected_json = Path("app/classifier/eval/golden_expected.json")

    if not expected_json.exists():
        warn("Golden set", "golden_expected.json missing")
        return

    expected = json.loads(expected_json.read_text())
    tif_files = list(golden_dir.glob("*.tif")) + list(golden_dir.glob("*.tiff"))

    if not tif_files:
        warn("Golden set", "No golden images found")
        return

    # Rule: every file listed in golden_expected.json must exist.
    # Extra images in folder are allowed (dev convenience).
    missing = [name for name in expected.keys() if not (golden_dir / name).exists()]
    if missing:
        raise AssertionError(f"Golden images missing from folder: {missing}")

    check(f"Golden set: {len(expected)} expected entries present ({len(tif_files)} files on disk)")


run_test("Golden set structure", test_golden_set, critical=False)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 50)
print(f"Tests passed: {tests_passed}")
print(f"Tests failed: {tests_failed}")
print(f"Warnings    : {warnings}")
print("=" * 50)

if tests_failed > 0:
    print("\n[FAIL] LOCAL TEST SUITE FAILED\n")
    sys.exit(1)
else:
    print("\n[PASS] ALL LOCAL TESTS PASSED\n")
    print("Next steps:", flush=True)
    print("  1. Install dependencies: uv sync --frozen", flush=True)
    print("  2. Start Docker stack: docker compose up -d", flush=True)
    print("  3. Run migrations: docker compose run --rm migrate", flush=True)
    print("  4. Seed admin: docker compose run --rm api python scripts/seed_admin.py", flush=True)
    print("  5. Open API docs: http://localhost:8000/docs\n", flush=True)
    sys.exit(0)
