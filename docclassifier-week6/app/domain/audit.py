from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    actor_id: Optional[str]
    action: str
    target: str
    details: Optional[dict[str, Any]] = None
    timestamp: datetime

    model_config = {"from_attributes": True}
