"""Trade-related models: 1099, monthly, matched, annotations, account summaries."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Trade1099(Base):
    __tablename__ = "trades_1099"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[Optional[int]] = mapped_column(ForeignKey("imports.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(20))
    date_sold: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    date_acquired: Mapped[Optional[str]] = mapped_column(String(10))
    date_acquired_raw: Mapped[Optional[str]] = mapped_column(String(50))
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    proceeds: Mapped[float] = mapped_column(Float, nullable=False)
    cost_basis: Mapped[float] = mapped_column(Float, nullable=False)
    wash_sale_disallowed: Mapped[float] = mapped_column(Float, server_default="0")
    gain_loss: Mapped[float] = mapped_column(Float, nullable=False)
    term: Mapped[str] = mapped_column(String(10), nullable=False)
    covered: Mapped[int] = mapped_column(Integer, nullable=False)
    form_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_type: Mapped[Optional[str]] = mapped_column(String(20))
    asset_type: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(20))
    holding_days: Mapped[Optional[int]] = mapped_column(Integer)
    holding_period_type: Mapped[Optional[str]] = mapped_column(String(20))
    underlying_symbol: Mapped[Optional[str]] = mapped_column(String(20))


class TradeMonthly(Base):
    __tablename__ = "trades_monthly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[Optional[int]] = mapped_column(ForeignKey("imports.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cusip: Mapped[Optional[str]] = mapped_column(String(20))
    acct_type: Mapped[Optional[str]] = mapped_column(String(20))
    transaction_type: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    is_option: Mapped[int] = mapped_column(Integer, server_default="0")
    option_detail: Mapped[Optional[str]] = mapped_column(Text)
    is_recurring: Mapped[int] = mapped_column(Integer, server_default="0")
    asset_type: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(20))
    underlying_symbol: Mapped[Optional[str]] = mapped_column(String(20))


class MatchedTrade(Base):
    __tablename__ = "matched_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    buy_date: Mapped[str] = mapped_column(String(10), nullable=False)
    sell_date: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    buy_price: Mapped[float] = mapped_column(Float, nullable=False)
    sell_price: Mapped[float] = mapped_column(Float, nullable=False)
    buy_amount: Mapped[float] = mapped_column(Float, nullable=False)
    sell_amount: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_type: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(20))
    holding_period_type: Mapped[Optional[str]] = mapped_column(String(20))
    underlying_symbol: Mapped[Optional[str]] = mapped_column(String(20))


class AccountSummary(Base):
    __tablename__ = "account_summaries"
    __table_args__ = (
        UniqueConstraint("user_id", "account", "period_start", "period_end",
                         name="uq_account_summary_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[Optional[int]] = mapped_column(ForeignKey("imports.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    account: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)
    opening_balance: Mapped[float] = mapped_column(Float, nullable=False)
    closing_balance: Mapped[float] = mapped_column(Float, nullable=False)


class TradeAnnotation(Base):
    __tablename__ = "trade_annotations"
    __table_args__ = (
        UniqueConstraint("user_id", "source", "symbol", "trade_date", "quantity",
                         name="uq_annotation_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(Float)
    strategy_tag: Mapped[Optional[str]] = mapped_column(String(30))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
