"""
SQLAlchemy ORM Models — aligned with domain models in app/domain/.

These map to database tables but should NOT be returned directly from repositories.
Repositories convert these to domain Pydantic models before returning to services.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Float, ForeignKey, Index, JSON, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.domain.user import Role
from app.domain.batch import BatchStatus


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True)
    email:           Mapped[str]      = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str]      = mapped_column(String(255), nullable=False)
    role:            Mapped[Role]     = mapped_column(String(50),  nullable=False, default=Role.auditor)
    is_active:       Mapped[bool]     = mapped_column(default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    audit_entries: Mapped[List["AuditLog"]] = relationship(back_populates="actor", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"User(id={self.id}, email={self.email}, role={self.role})"


class Batch(Base):
    __tablename__ = "batches"

    id:         Mapped[str]         = mapped_column(String(36), primary_key=True)
    status:     Mapped[BatchStatus] = mapped_column(String(50), nullable=False, default=BatchStatus.pending)
    file_count: Mapped[int]         = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime]    = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    predictions: Mapped[List["Prediction"]] = relationship(back_populates="batch", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_batch_status",  "status"),
        Index("idx_batch_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"Batch(id={self.id}, status={self.status}, file_count={self.file_count})"


class Prediction(Base):
    __tablename__ = "predictions"

    id:              Mapped[str]           = mapped_column(String(36), primary_key=True)
    batch_id:        Mapped[str]           = mapped_column(String(36), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False)
    filename:        Mapped[str]           = mapped_column(String(512), nullable=False)
    blob_key:        Mapped[str]           = mapped_column(String(512), nullable=False)
    overlay_key:     Mapped[str]           = mapped_column(String(512), nullable=False)
    predicted_class: Mapped[str]           = mapped_column(String(100), nullable=False)
    confidence:      Mapped[float]         = mapped_column(Float, nullable=False)
    relabeled_class: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at:      Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at:      Mapped[datetime]      = mapped_column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    batch: Mapped["Batch"] = relationship(back_populates="predictions")

    __table_args__ = (
        Index("idx_prediction_batch",           "batch_id"),
        Index("idx_prediction_predicted_class", "predicted_class"),
    )

    def __repr__(self) -> str:
        return f"Prediction(id={self.id}, batch_id={self.batch_id}, predicted_class={self.predicted_class})"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:        Mapped[str]           = mapped_column(String(36), primary_key=True)
    actor_id:  Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action:    Mapped[str]           = mapped_column(String(100), nullable=False)
    target:    Mapped[str]           = mapped_column(String(255), nullable=False)
    details:   Mapped[Optional[dict]]= mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    actor: Mapped[Optional["User"]] = relationship(back_populates="audit_entries")

    def __repr__(self) -> str:
        return f"AuditLog(id={self.id}, action={self.action}, actor_id={self.actor_id})"
