"""Wash sale detection and analysis."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd


def detect_wash_sales(df: pd.DataFrame) -> pd.DataFrame:
    """Analyze wash sale exposure from 1099 data.

    Returns a DataFrame with wash sale summary by symbol.
    """
    if df.empty:
        return pd.DataFrame()

    wash = df[df["wash_sale_disallowed"] > 0].copy()
    if wash.empty:
        return pd.DataFrame(columns=[
            "symbol", "total_wash_disallowed", "num_wash_trades",
            "first_wash_date", "last_wash_date",
        ])

    summary = wash.groupby("symbol").agg(
        total_wash_disallowed=("wash_sale_disallowed", "sum"),
        num_wash_trades=("wash_sale_disallowed", "count"),
        first_wash_date=("trade_date", "min"),
        last_wash_date=("trade_date", "max"),
    ).reset_index()

    summary = summary.sort_values("total_wash_disallowed", ascending=False)
    return summary


def get_wash_sale_timeline(df: pd.DataFrame) -> pd.DataFrame:
    """Get monthly wash sale amounts for timeline visualization."""
    if df.empty:
        return pd.DataFrame()

    wash = df[df["wash_sale_disallowed"] > 0].copy()
    if wash.empty:
        return pd.DataFrame()

    wash["month"] = wash["trade_date"].dt.to_period("M")
    timeline = wash.groupby("month").agg(
        wash_amount=("wash_sale_disallowed", "sum"),
        num_trades=("wash_sale_disallowed", "count"),
    ).reset_index()
    timeline["month"] = timeline["month"].astype(str)
    return timeline
