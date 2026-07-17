"""Fundamentals Engine tables — EDGAR-sourced deep fundamentals.

Distinct from ``symbol_fundamentals`` (the Finnhub/AI Details-tab snapshot):
these tables hold the multi-quarter time series and derived
red-flag / value analysis from SEC XBRL, per the Fundamentals Engine spec.

Five tables mirror the spec's conceptual model:
  * ``fund_company``     — ticker ↔ CIK + profile
  * ``fund_financials``  — per-period normalised line items (+ source filing)
  * ``fund_metric``      — per-period computed metric (long format, extensible)
  * ``fund_score``       — per-symbol as-of quality & risk score
  * ``fund_flag``        — per-symbol as-of red/value flags (dedup for alerts)

Shared across users (financials are the same for everyone); the per-user
watchlist scoping lives in the existing ``watchlist`` table. Populated by
analytics/fundamentals_engine_refresh.py on the nightly cron. Every row carries
provenance (source filing / as-of) so numbers are auditable.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FundCompany(Base):
    """Ticker → CIK mapping + light profile. One row per symbol."""

    __tablename__ = "fund_company"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    cik: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    exchange: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Set when EDGAR has no XBRL fundamentals for this symbol (ETF/ADR/IPO) so
    # the nightly batch can skip it fast without re-resolving every run.
    no_edgar_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FundFinancials(Base):
    """One reporting period's normalised line items + source filing.

    Idempotent on (symbol, period_end, form): re-running the nightly batch
    updates the row in place rather than duplicating (NFR: idempotent pulls).
    """

    __tablename__ = "fund_financials"
    __table_args__ = (
        UniqueConstraint("symbol", "period_end", "form", name="uq_fund_financials_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    form: Mapped[str] = mapped_column(String(8), nullable=False)          # 10-K / 10-Q
    fiscal_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fiscal_period: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    filed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    accession: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Line items (all nullable — missing stays missing).
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_of_revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_income: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    interest_expense: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    operating_cash_flow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    capex: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inventory: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    receivables: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_current_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_current_liabilities: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_assets: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_liabilities: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cash: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    short_term_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    long_term_debt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stockholders_equity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    shares_diluted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class FundMetric(Base):
    """One computed metric for one period. Long format so new Phase-2 ratios
    plug in with zero schema change (NFR: extensibility)."""

    __tablename__ = "fund_metric"
    __table_args__ = (
        UniqueConstraint("symbol", "period_end", "name", name="uq_fund_metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    threshold_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FundScore(Base):
    """Per-symbol quality & risk score as-of a run date. Latest row per symbol
    drives the dashboard; history accrues for Phase-2 backtesting."""

    __tablename__ = "fund_score"
    __table_args__ = (
        UniqueConstraint("symbol", "as_of_date", name="uq_fund_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profitable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    quality_coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_coverage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latest_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FundFlag(Base):
    """A red/value flag raised for a symbol as-of a run date.

    Dedup on (symbol, code, as_of_date) so re-running a day is idempotent and
    the alert layer can tell a genuinely NEW flag from a repeat."""

    __tablename__ = "fund_flag"
    __table_args__ = (
        UniqueConstraint("symbol", "code", "as_of_date", name="uq_fund_flag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False)   # info/warn/critical
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metric: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
