"""Add notification preference columns to users table.

Revision ID: 002_notification_prefs
Revises: 001_device_tokens
Create Date: 2026-03-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_notification_prefs"
down_revision = "001_device_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_enabled", sa.Boolean(), server_default="1", nullable=True))
    op.add_column("users", sa.Column("email_enabled", sa.Boolean(), server_default="0", nullable=True))
    op.add_column("users", sa.Column("push_enabled", sa.Boolean(), server_default="0", nullable=True))
    op.add_column("users", sa.Column("quiet_hours_start", sa.String(length=10), nullable=True))
    op.add_column("users", sa.Column("quiet_hours_end", sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "quiet_hours_end")
    op.drop_column("users", "quiet_hours_start")
    op.drop_column("users", "push_enabled")
    op.drop_column("users", "email_enabled")
    op.drop_column("users", "telegram_enabled")
