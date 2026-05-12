# Location: app/domain/user.py
# Purpose: Pydantic schema for User representation (output of service layer)

from pydantic import BaseModel
from uuid import UUID

class User(BaseModel):
    id: UUID
    email: str
    role: str          # "admin", "reviewer", "auditor"
    is_active: bool

    class Config:
        from_attributes = True   # enables .from_orm() / model_validate with ORM objects