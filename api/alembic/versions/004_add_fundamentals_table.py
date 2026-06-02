"""Add symbol_fundamentals table.

Watchlist > Details tab — one row per symbol caching Finnhub fundamentals +
analyst ratings + yfinance description + Anthropic short/long-term views.
Populated on-demand (no nightly cron) via analytics/fundamentals_refresh.py.

Note: the running app also auto-creates this via Base.metadata.create_all in
the FastAPI lifespan; this migration keeps Alembic in sync for fresh DBs.

Revision ID: 004_fundamentals_table
Revises: 003_earnings_tables
Create Date: 2026-06-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "004_fundamentals_table"
down_revision = "003_earnings_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbol_fundamentals",
        sa.Column("symbol", sa.String(length=20), primary_key=True),
        sa.Column("company_name", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sector", sa.String(length=80), nullable=True),
        sa.Column("industry", sa.String(length=120), nullable=True),
        sa.Column("market_cap", sa.Float(), nullable=True),
        sa.Column("trailing_eps", sa.Float(), nullable=True),
        sa.Column("forward_eps", sa.Float(), nullable=True),
        sa.Column("eps_growth_pct", sa.Float(), nullable=True),
        sa.Column("pe_ratio", sa.Float(), nullable=True),
        sa.Column("rec_strong_buy", sa.Integer(), nullable=True),
        sa.Column("rec_buy", sa.Integer(), nullable=True),
        sa.Column("rec_hold", sa.Integer(), nullable=True),
        sa.Column("rec_sell", sa.Integer(), nullable=True),
        sa.Column("rec_strong_sell", sa.Integer(), nullable=True),
        sa.Column("consensus", sa.String(length=16), nullable=True),
        sa.Column("rec_period", sa.String(length=12), nullable=True),
        sa.Column("short_term_view", sa.Text(), nullable=True),
        sa.Column("long_term_view", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("symbol_fundamentals")
