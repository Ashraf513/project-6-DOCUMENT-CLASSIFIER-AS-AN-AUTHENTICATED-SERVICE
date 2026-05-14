"""initial

Revision ID: dfd74b4da8d3
Revises:
Create Date: 2026-05-13 18:19:59.821211

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dfd74b4da8d3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='auditor'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'batches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('file_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_batch_status', 'batches', ['status'])
    op.create_index('idx_batch_created', 'batches', ['created_at'])

    op.create_table(
        'predictions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(512), nullable=False),
        sa.Column('blob_key', sa.String(512), nullable=False),
        sa.Column('overlay_key', sa.String(512), nullable=False),
        sa.Column('predicted_class', sa.String(100), nullable=False),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('relabeled_class', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_prediction_batch', 'predictions', ['batch_id'])
    op.create_index('idx_prediction_predicted_class', 'predictions', ['predicted_class'])

    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('target', sa.String(255), nullable=False),
        sa.Column('details', sa.JSON, nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_audit_logs_timestamp', 'audit_logs', ['timestamp'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('predictions')
    op.drop_table('batches')
    op.drop_table('users')
