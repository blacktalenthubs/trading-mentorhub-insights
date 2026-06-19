"""Add target_kind / trade_type / swing_eligible to alerts.

Sub-spec A/L (#64) — the single-target model (target_kind: level|rsi|eod) and the
day/swing classification (trade_type + swing_eligible). Also added live by db.py's
_safe_add_column ALTERs (worker) and by create_all on a fresh DB; this migration
keeps Alembic in sync.

Revision ID: 007_target_kind
Revises: 006_strategy_week_ai
Create Date: 2026-06-19
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "007_target_kind"
down_revision = "006_strategy_week_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("target_kind", sa.String(length=10), nullable=True))
    op.add_column("alerts", sa.Column("trade_type", sa.String(length=10), nullable=True))
    op.add_column(
        "alerts",
        sa.Column("swing_eligible", sa.Integer(), server_default="0", nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alerts", "swing_eligible")
    op.drop_column("alerts", "trade_type")
    op.drop_column("alerts", "target_kind")
