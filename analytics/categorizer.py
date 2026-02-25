"""Enrich trade records with categories and derived fields."""

from __future__ import annotations

from config import categorize_symbol, classify_holding_period, detect_asset_type
from models import Trade1099, TradeMonthly


def enrich_trades(trades: list[Trade1099]) -> list[Trade1099]:
    """Re-compute derived fields on 1099 trades (idempotent)."""
    for t in trades:
        if not t.asset_type:
            t.asset_type = detect_asset_type(t.description, t.symbol)
        if not t.category:
            sym = t.underlying_symbol if t.underlying_symbol else t.symbol.split()[0]
            t.category = categorize_symbol(sym)
        if t.holding_days is not None and not t.holding_period_type:
            t.holding_period_type = classify_holding_period(t.holding_days)
    return trades
