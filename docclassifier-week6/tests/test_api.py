# File: tests/test_api.py
from app.api.routers.auth import current_active_user
from app.domain.user import User, Role
from datetime import datetime

async def override_current_user():
    return User(
        id="1",
        email="test@test.com",
        role=Role.admin,
        is_active=True,
        created_at=datetime.utcnow(),
    )

app.dependency_overrides[current_active_user] = override_current_user

import os

os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import (
    get_batch_service,
    get_prediction_service,
    get_user_service,
)

client = TestClient(app)


# =========================
# MOCK SERVICES
# =========================

class MockBatchService:
    async def list_batches(self, skip=0, limit=20):
        return [
            {
                "id": "batch-1",
                "status": "completed",
            }
        ]

    async def get_batch(self, batch_id):
        return {
            "id": batch_id,
            "status": "completed",
        }


class MockPredictionService:
    async def get_recent_predictions(self, limit=10):
        return [
            {
                "id": "pred-1",
                "label": "invoice",
                "confidence": 0.92,
            }
        ]

    async def get_predictions_for_batch(self, batch_id):
        return [
            {
                "id": "pred-1",
                "batch_id": batch_id,
            }
        ]


class MockUserService:
    async def get_me(self, user_id):
        return {
            "id": user_id,
            "email": "test@test.com",
            "role": "admin",
        }

    async def list_users(self, actor, skip=0, limit=20):
        return [
            {
                "id": "1",
                "email": "test@test.com",
            }
        ]


# =========================
# DEPENDENCY OVERRIDES
# =========================

async def override_batch_service():
    return MockBatchService()


async def override_prediction_service():
    return MockPredictionService()


async def override_user_service():
    return MockUserService()


app.dependency_overrides[get_batch_service] = override_batch_service
app.dependency_overrides[get_prediction_service] = override_prediction_service
app.dependency_overrides[get_user_service] = override_user_service


# =========================
# TESTS
# =========================

def test_health():
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "healthy"


def test_list_batches():
    response = client.get("/batches/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    assert data[0]["id"] == "batch-1"


def test_get_batch():
    response = client.get("/batches/batch-1")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == "batch-1"


def test_recent_predictions():
    response = client.get("/predictions/recent")

    assert response.status_code == 200

    data = response.json()

    assert data[0]["label"] == "invoice"


def test_predictions_for_batch():
    response = client.get("/predictions/batch/batch-1")

    assert response.status_code == 200

    data = response.json()

    assert data[0]["batch_id"] == "batch-1"


def test_list_users():
    response = client.get("/users/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1


def test_get_me():
    response = client.get("/users/me")

    assert response.status_code == 200