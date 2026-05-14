"""
Domain model for a user.

fastapi-users manages authentication internals (hashed password, JWT).
This domain model is what the rest of the application sees — a clean
object with role and status, no auth implementation details.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr


class Role(str, Enum):
    admin    = "admin"     # invite users, toggle roles, view audit log
    reviewer = "reviewer"  # view batches, relabel predictions with confidence < 0.7
    auditor  = "auditor"   # read-only on batches and audit log


class User(BaseModel):
    id:         str
    email:      EmailStr
    role:       Role
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    """Input shape for user registration."""
    email:    EmailStr
    password: str
    role:     Role = Role.auditor   # new users default to least-privileged role


class UserRoleUpdate(BaseModel):
    """Input shape for the admin role-toggle endpoint."""
    role: Role
    
class UserRead(BaseModel):
    """Public user representation (no password hash)."""
    id:         str
    email:      EmailStr
    role:       Role
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    """Optional fields a user can update on their own profile."""
    email:     EmailStr | None = None
    password:  str | None = None
    is_active: bool | None = None