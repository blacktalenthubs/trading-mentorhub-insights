"""Add Fundamentals Engine tables (EDGAR-sourced deep fundamentals).

Five tables backing the Fundamentals Engine: fund_company, fund_financials,
fund_metric, fund_score, fund_flag. Distinct from symbol_fundamentals (the
Finnhub/AI Details snapshot) — these hold the multi-quarter XBRL time series
plus the derived red-flag / value analysis.

The running app also auto-creates these via Base.metadata.create_all in the
FastAPI lifespan; this migration keeps Alembic in sync for fresh DBs.

Revision ID: 008_fundamentals_engine
Revises: 007_target_kind
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "008_fundamentals_engine"
down_revision = "007_target_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fund_company",
        sa.Column("symbol", sa.String(length=20), primary_key=True),
        sa.Column("cik", sa.Integer(), nullable=True),
        sa.Column("company_name", sa.String(length=160), nullable=True),
        sa.Column("sector", sa.String(length=80), nullable=True),
        sa.Column("exchange", sa.String(length=40), nullable=True),
        sa.Column("no_edgar_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fund_company_cik", "fund_company", ["cik"])

    op.create_table(
        "fund_financials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("form", sa.String(length=8), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=4), nullable=True),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("period_days", sa.Integer(), nullable=True),
        sa.Column("accession", sa.String(length=30), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("cost_of_revenue", sa.Float(), nullable=True),
        sa.Column("gross_profit", sa.Float(), nullable=True),
        sa.Column("operating_income", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("interest_expense", sa.Float(), nullable=True),
        sa.Column("operating_cash_flow", sa.Float(), nullable=True),
        sa.Column("capex", sa.Float(), nullable=True),
        sa.Column("inventory", sa.Float(), nullable=True),
        sa.Column("receivables", sa.Float(), nullable=True),
        sa.Column("total_current_assets", sa.Float(), nullable=True),
        sa.Column("total_current_liabilities", sa.Float(), nullable=True),
        sa.Column("total_assets", sa.Float(), nullable=True),
        sa.Column("total_liabilities", sa.Float(), nullable=True),
        sa.Column("cash", sa.Float(), nullable=True),
        sa.Column("short_term_debt", sa.Float(), nullable=True),
        sa.Column("long_term_debt", sa.Float(), nullable=True),
        sa.Column("stockholders_equity", sa.Float(), nullable=True),
        sa.Column("shares_diluted", sa.Float(), nullable=True),
        sa.UniqueConstraint("symbol", "period_end", "form", name="uq_fund_financials_period"),
    )
    op.create_index("ix_fund_financials_symbol", "fund_financials", ["symbol"])

    op.create_table(
        "fund_metric",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=12), nullable=True),
        sa.Column("threshold_breached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("symbol", "period_end", "name", name="uq_fund_metric"),
    )
    op.create_index("ix_fund_metric_symbol", "fund_metric", ["symbol"])

    op.create_table(
        "fund_score",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("profitable", sa.Boolean(), nullable=True),
        sa.Column("quality_coverage", sa.Float(), nullable=True),
        sa.Column("risk_coverage", sa.Float(), nullable=True),
        sa.Column("latest_period_end", sa.Date(), nullable=True),
        sa.Column("computed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("symbol", "as_of_date", name="uq_fund_score"),
    )
    op.create_index("ix_fund_score_symbol", "fund_score", ["symbol"])

    op.create_table(
        "fund_flag",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=12), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metric", sa.String(length=40), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("symbol", "code", "as_of_date", name="uq_fund_flag"),
    )
    op.create_index("ix_fund_flag_symbol", "fund_flag", ["symbol"])


def downgrade() -> None:
    op.drop_table("fund_flag")
    op.drop_table("fund_score")
    op.drop_table("fund_metric")
    op.drop_table("fund_financials")
    op.drop_table("fund_company")
