# Location: app/services/__init__.py
# Re-export the three service classes so routers can do:
#   from app.services import UserService, BatchService, PredictionService

from app.services.user_service import UserService
from app.services.batch_service import BatchService
from app.services.prediction_service import PredictionService

__all__ = ["UserService", "BatchService", "PredictionService"]
