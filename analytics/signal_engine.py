"""Signal scoring engine — actionable trade plans per symbol.

For each symbol, determines:
- Where is support? (prior day low, MA20, MA50)
- What is the support status? (HOLDING / TESTING / BROKEN)
- What is the trade plan? (entry, stop, target, re-entry)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analytics.market_data import classify_day, fetch_ohlc, get_levels


@dataclass
class SignalResult:
    """Trade plan for a single symbol."""

    symbol: str
    last_close: float
    prior_high: float
    prior_low: float

    # Support analysis
    nearest_support: float
    support_label: str  # "Prior Day Low", "20 MA", "50 MA"
    support_status: str  # "AT SUPPORT", "PULLBACK WATCH", "BREAKOUT", "BROKEN"
    distance_to_support: float  # $ distance (positive = above, negative = below)
    distance_pct: float  # % distance

    # Trade plan
    entry: float
    stop: float
    target_1: float
    target_2: float
    reentry_stop: float  # stop for 2nd attempt (wider)
    risk_per_share: float
    rr_ratio: float

    # Context
    pattern: str  # inside / outside / normal
    direction: str  # bullish / bearish / neutral
    bias: str  # one-line trade bias
    day_range: float

    # MA data
    ma20: float | None = None
    ma50: float | None = None

    # Volume
    avg_volume: float = 0.0
    last_volume: float = 0.0
    volume_ratio: float = 0.0


# ---------------------------------------------------------------------------
# Actionable display labels
# ---------------------------------------------------------------------------

ACTION_LABELS = {
    "AT SUPPORT": {"label": "BUY ZONE", "color": "#2ecc71", "help": "Price at support — place entry order"},
    "BREAKOUT": {"label": "BREAKOUT SETUP", "color": "#3498db", "help": "Inside day compression — set alert at breakout level"},
    "PULLBACK WATCH": {"label": "WAIT FOR DIP", "color": "#f39c12", "help": "Above support — wait for pullback to entry"},
    "BROKEN": {"label": "NO TRADE", "color": "#e74c3c", "help": "Support broken — no valid long setup"},
}


def action_label(support_status: str) -> str:
    """Map internal support status to user-facing action label."""
    return ACTION_LABELS.get(support_status, {}).get("label", support_status)


def action_color(support_status: str) -> str:
    """Get the display color for a support status."""
    return ACTION_LABELS.get(support_status, {}).get("color", "#95a5a6")


def action_help(support_status: str) -> str:
    """Get the help text for a support status."""
    return ACTION_LABELS.get(support_status, {}).get("help", "")


# ---------------------------------------------------------------------------
# Support status logic
# ---------------------------------------------------------------------------

def _find_nearest_support(
    close: float,
    prior_low: float,
    ma20: float | None,
    ma50: float | None,
) -> tuple[float, str]:
    """Find the nearest support level below or at the current price."""
    candidates = []
    if prior_low > 0:
        candidates.append((prior_low, "Prior Day Low"))
    if ma20 is not None and ma20 > 0:
        candidates.append((ma20, "20 MA"))
    if ma50 is not None and ma50 > 0:
        candidates.append((ma50, "50 MA"))

    if not candidates:
        return prior_low, "Prior Day Low"

    # Find the nearest support AT or BELOW the current price
    below = [(lvl, label) for lvl, label in candidates if lvl <= close]
    if below:
        # Closest support below
        below.sort(key=lambda x: close - x[0])
        return below[0]

    # All supports are above price (price broke everything) — return lowest
    candidates.sort(key=lambda x: x[0])
    return candidates[0]


def _classify_support_status(
    close: float,
    low: float,
    support: float,
    pattern: str,
) -> str:
    """Classify how price relates to its nearest support."""
    if support <= 0:
        return "NO DATA"

    pct_from_support = (close - support) / support * 100

    # Did today's low wick below support but close recovered?
    wicked_below = low < support and close >= support
    if wicked_below:
        return "AT SUPPORT"  # reclaim pattern — best entry

    if pattern == "inside":
        return "BREAKOUT"  # inside day = compression, different setup

    if close < support:
        return "BROKEN"  # closed below support

    if pct_from_support <= 0.5:
        return "AT SUPPORT"  # within 0.5% of support

    return "PULLBACK WATCH"  # above support, wait for pullback


# ---------------------------------------------------------------------------
# Trade plan builder
# ---------------------------------------------------------------------------

def _build_trade_plan(
    levels: dict,
    support: float,
    support_status: str,
    pattern: str,
) -> dict:
    """Build entry/stop/target/re-entry based on support status and pattern."""
    entry = levels["entry_long"]
    stop = levels["stop_long"]
    target_1 = levels["target_1"]
    target_2 = levels["target_2"]
    risk = levels["risk_per_share"]

    # Re-entry stop: $1.50 wider than original stop (from SPY pattern analysis)
    reentry_stop = stop - 1.50

    # For broken support, keep the levels for reference but flag it
    if support_status == "BROKEN":
        # Entry would be at the next support below, but we don't have it
        # Keep original levels for reference
        pass

    rr = (target_1 - entry) / risk if risk > 0 else 0

    return {
        "entry": entry,
        "stop": stop,
        "target_1": target_1,
        "target_2": target_2,
        "reentry_stop": reentry_stop,
        "risk_per_share": risk,
        "rr_ratio": rr,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze_symbol(hist: pd.DataFrame, symbol: str = "") -> SignalResult | None:
    """Analyze a symbol and return an actionable trade plan."""
    if hist.empty or len(hist) < 2:
        return None

    hist = hist.copy()
    hist["MA20"] = hist["Close"].rolling(window=20).mean()
    hist["MA50"] = hist["Close"].rolling(window=50).mean()

    last_idx = len(hist) - 1
    row = hist.iloc[last_idx]
    prev_row = hist.iloc[last_idx - 1]

    pattern, direction = classify_day(row, prev_row)
    levels = get_levels(hist, last_idx)

    close = row["Close"]
    high = row["High"]
    low = row["Low"]
    prior_low = prev_row["Low"]
    prior_high = prev_row["High"]
    day_range = high - low
    ma20 = hist["MA20"].iloc[last_idx] if pd.notna(hist["MA20"].iloc[last_idx]) else None
    ma50 = hist["MA50"].iloc[last_idx] if pd.notna(hist["MA50"].iloc[last_idx]) else None

    # Volume
    last_vol = row["Volume"]
    avg_vol = hist["Volume"].rolling(window=20).mean().iloc[last_idx]
    if pd.isna(avg_vol):
        avg_vol = hist["Volume"].mean()
    vol_ratio = last_vol / avg_vol if avg_vol > 0 else 1.0

    # Support analysis
    support, support_label = _find_nearest_support(close, prior_low, ma20, ma50)
    support_status = _classify_support_status(close, low, support, pattern)
    dist = close - support
    dist_pct = (dist / support * 100) if support > 0 else 0

    # Trade plan
    plan = _build_trade_plan(levels, support, support_status, pattern)

    # One-line bias
    bias = levels.get("bias", "")

    return SignalResult(
        symbol=symbol,
        last_close=close,
        prior_high=prior_high,
        prior_low=prior_low,
        nearest_support=support,
        support_label=support_label,
        support_status=support_status,
        distance_to_support=dist,
        distance_pct=dist_pct,
        entry=plan["entry"],
        stop=plan["stop"],
        target_1=plan["target_1"],
        target_2=plan["target_2"],
        reentry_stop=plan["reentry_stop"],
        risk_per_share=plan["risk_per_share"],
        rr_ratio=plan["rr_ratio"],
        pattern=pattern,
        direction=direction,
        bias=bias,
        day_range=day_range,
        ma20=ma20,
        ma50=ma50,
        avg_volume=avg_vol,
        last_volume=last_vol,
        volume_ratio=vol_ratio,
    )


def scan_watchlist(
    symbols: list[str],
    period: str = "3mo",
) -> list[SignalResult]:
    """Fetch data and analyze each symbol. Returns results sorted by proximity to support."""
    results: list[SignalResult] = []
    for sym in symbols:
        sym = sym.upper().strip()
        if not sym:
            continue
        hist = fetch_ohlc(sym, period)
        if hist.empty:
            continue
        result = analyze_symbol(hist, sym)
        if result is not None:
            results.append(result)

    # Sort: AT SUPPORT first, then BREAKOUT, then PULLBACK WATCH, then BROKEN
    status_order = {"AT SUPPORT": 0, "BREAKOUT": 1, "PULLBACK WATCH": 2, "BROKEN": 3, "NO DATA": 4}
    results.sort(key=lambda r: (status_order.get(r.support_status, 4), abs(r.distance_pct)))
    return results
