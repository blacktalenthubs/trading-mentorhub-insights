"""Data models for trade analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Trade1099:
    """A completed trade from 1099-B or 1099-DA."""
    account: str
    description: str
    symbol: str
    cusip: str
    date_sold: date
    date_acquired: Optional[date]  # None if "Various"
    date_acquired_raw: str  # original text e.g. "Various"
    quantity: float
    proceeds: float
    cost_basis: float
    wash_sale_disallowed: float
    gain_loss: float
    term: str  # "short", "long", "undetermined"
    covered: bool  # True = covered, False = noncovered
    form_type: str  # "1099-B" or "1099-DA"
    trade_type: str  # "Sale", "Option sale", "Option expiration", "Total of N transactions"
    asset_type: str = ""  # stock, option, etf, crypto
    category: str = ""  # mega_cap, speculative, index_etf, crypto, other
    holding_days: Optional[int] = None
    holding_period_type: str = ""  # day_trade, swing, position, unknown
    underlying_symbol: str = ""  # for options: the underlying ticker


@dataclass
class TradeMonthly:
    """An individual buy/sell from a monthly statement."""
    account: str
    description: str
    symbol: str
    cusip: str
    acct_type: str  # "Cash", "Margin"
    transaction_type: str  # "Buy", "Sell", "BTO", "STC"
    trade_date: date
    quantity: float
    price: float
    amount: float  # debit (negative) or credit (positive)
    is_option: bool = False
    option_detail: str = ""  # e.g. "SPY 01/29/2026 Call $696.00"
    is_recurring: bool = False
    asset_type: str = ""
    category: str = ""
    underlying_symbol: str = ""


@dataclass
class MatchedTrade:
    """A FIFO-paired buy/sell from monthly data."""
    account: str
    symbol: str
    buy_date: date
    sell_date: date
    quantity: float
    buy_price: float
    sell_price: float
    buy_amount: float
    sell_amount: float
    realized_pnl: float
    holding_days: int
    asset_type: str = ""
    category: str = ""
    holding_period_type: str = ""
    underlying_symbol: str = ""


@dataclass
class AccountSummary:
    """Monthly account balance snapshot."""
    account: str
    period_start: date
    period_end: date
    opening_balance: float
    closing_balance: float


@dataclass
class ImportRecord:
    """Tracks an imported PDF."""
    filename: str
    file_type: str  # "1099" or "monthly_statement"
    period: str  # e.g. "2025" or "2026-01"
    records_imported: int = 0
