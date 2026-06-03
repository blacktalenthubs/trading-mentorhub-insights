"""Add strategy_week_ai_cache table.

Per-week cache for the AI strategy-analysis verdicts (Daily/Weekly redesign).
Keyed by the Monday ISO date of the week. Also auto-created by create_all on
startup; this migration keeps Alembic in sync for fresh DBs.

Revision ID: 006_strategy_week_ai
Revises: 005_forward_returns
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "006_strategy_week_ai"
down_revision = "005_forward_returns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_week_ai_cache",
        sa.Column("week_start", sa.String(length=10), primary_key=True),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("verdicts_json", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_week_ai_cache")
