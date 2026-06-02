"""Add forward-return columns to alerts + strategy_analysis_cache table.

Strategy Analysis feature — real close-to-close forward returns (EOD + EOW)
per alert, aggregated by pattern to decide which to keep/stop/promote.

Note: the running app also auto-adds the columns via the ALTER-TABLE-IF-NOT-EXISTS
block in the FastAPI lifespan (create_all does NOT alter existing tables) and
auto-creates the cache table via create_all; this migration keeps Alembic in
sync for fresh DBs.

Revision ID: 005_forward_returns
Revises: 004_fundamentals_table
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "005_forward_returns"
down_revision = "004_fundamentals_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("ret_eod_pct", sa.Float(), nullable=True))
    op.add_column("alerts", sa.Column("ret_eow_pct", sa.Float(), nullable=True))
    op.add_column("alerts", sa.Column("fwd_returns_computed_at", sa.DateTime(), nullable=True))

    op.create_table(
        "strategy_analysis_cache",
        sa.Column("lookback_days", sa.Integer(), primary_key=True),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("strategy_analysis_cache")
    op.drop_column("alerts", "fwd_returns_computed_at")
    op.drop_column("alerts", "ret_eow_pct")
    op.drop_column("alerts", "ret_eod_pct")
