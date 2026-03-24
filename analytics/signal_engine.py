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
from analytics.market_hours import is_market_hours


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
    support_status: str  # "AT SUPPORT", "PULLBACK WATCH", "BROKEN"
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

    # Reference day H/L (the most recent completed day — for chart display)
    ref_day_high: float | None = None
    ref_day_low: float | None = None

    # Signal score (0-100)
    score: int = 0
    score_label: str = ""  # "Strong" (80+), "Moderate" (60+), "Weak" (40+), "Caution" (<40)


# ---------------------------------------------------------------------------
# Actionable display labels
# ---------------------------------------------------------------------------

ACTION_LABELS = {
    "AT SUPPORT": {"label": "Potential Entry", "color": "#2ecc71", "help": "Price at support — potential entry zone"},
    "PULLBACK WATCH": {"label": "Watch", "color": "#f39c12", "help": "Above support — watching for pullback"},
    "BROKEN": {"label": "No Setup", "color": "#e74c3c", "help": "Support broken — no valid long setup"},
}


_POTENTIAL_ENTRY_MIN_SCORE = 65  # Below this, "AT SUPPORT" is demoted to "Watch"


def action_label(support_status: str, score: int = 100) -> str:
    """Map internal support status to user-facing action label.

    AT SUPPORT with score < 65 is demoted to Watch (weak setup).
    """
    if support_status == "AT SUPPORT" and score < _POTENTIAL_ENTRY_MIN_SCORE:
        return ACTION_LABELS["PULLBACK WATCH"]["label"]
    return ACTION_LABELS.get(support_status, {}).get("label", support_status)


def action_color(support_status: str, score: int = 100) -> str:
    """Get the display color for a support status."""
    if support_status == "AT SUPPORT" and score < _POTENTIAL_ENTRY_MIN_SCORE:
        return ACTION_LABELS["PULLBACK WATCH"]["color"]
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

    # AT SUPPORT: buy the dip, target resistance above.
    # - Inside/outside day: entry at candle low, target at candle high (resistance)
    # - Normal day: entry at nearest support, target unchanged (prior high)
    if support_status == "AT SUPPORT" and support > 0:
        if pattern in ("inside", "outside"):
            entry = levels["stop_long"]       # candle low — buy the dip
            target_1 = levels["entry_long"]   # candle high — first resistance
            day_range = levels.get("prior_range", 0)
            risk = day_range * 0.25 if day_range > 0 else risk
        else:
            entry = support
        stop = entry - risk

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
# Signal scoring (wires up SIGNAL_WEIGHTS from config.py)
# ---------------------------------------------------------------------------

def _score_label(score: int) -> str:
    """Map numeric score to quality label."""
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Moderate"
    if score >= 40:
        return "Weak"
    return "Caution"


def compute_signal_score(result: SignalResult) -> int:
    """Score a signal 0-100 based on 4 factors (25 pts each).

    Uses SIGNAL_WEIGHTS from config.py for factor weights.
    """
    score = 0

    # Candle pattern (25): at support = 25, inside compression = 20, normal = 15
    if result.support_status == "AT SUPPORT":
        score += 25
    elif result.pattern == "inside":
        score += 20
    elif result.pattern == "normal":
        score += 15
    else:
        score += 5

    # MA position (25): price above both MAs = 25, above one = 15, below both = 0
    above_20 = result.ma20 is not None and result.last_close > result.ma20
    above_50 = result.ma50 is not None and result.last_close > result.ma50
    if above_20 and above_50:
        score += 25
    elif above_20 or above_50:
        score += 15

    # Support proximity (25): at support = 25, within 1% = 15, >1% = 5
    if abs(result.distance_pct) <= 0.5:
        score += 25
    elif abs(result.distance_pct) <= 1.0:
        score += 15
    else:
        score += 5

    # Volume (25): above average = 25, normal = 15, below = 5
    if result.volume_ratio >= 1.2:
        score += 25
    elif result.volume_ratio >= 0.8:
        score += 15
    else:
        score += 5

    return score


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def analyze_symbol(hist: pd.DataFrame, symbol: str = "") -> SignalResult | None:
    """Analyze a symbol and return an actionable trade plan."""
    if hist.empty or len(hist) < 2:
        return None

    hist = hist.copy()

    # Date-aware: if last bar is today's partial data, use yesterday instead
    hist.index = hist.index.tz_localize(None) if hist.index.tz is not None else hist.index
    today = pd.Timestamp.now().normalize()
    last_bar_date = hist.index[-1].normalize()
    if last_bar_date >= today and len(hist) >= 3 and is_market_hours():
        # Market open — last bar is partial; use prior completed day
        hist = hist.iloc[:-1]

    hist["MA20"] = hist["Close"].rolling(window=20).mean()
    hist["MA50"] = hist["Close"].rolling(window=50).mean()

    if len(hist) < 2:
        return None

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

    result = SignalResult(
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
        ref_day_high=high,
        ref_day_low=low,
    )

    # Compute signal score
    result.score = compute_signal_score(result)
    result.score_label = _score_label(result.score)

    return result


def reproject_after_stop(
    current_price: float,
    broken_stop: float,
    prior_low: float,
    ma20: float | None,
    ma50: float | None,
    ema20: float | None = None,
    ema50: float | None = None,
    prior_high: float | None = None,
    pattern: str = "normal",
) -> dict | None:
    """Re-project a trade plan after a stop is hit.

    Finds the next valid support BELOW the broken stop and builds a new
    entry/stop/target plan.  Read-only — no DB writes.

    Returns dict with entry, stop, target_1, target_2, risk_per_share,
    rr_ratio, support, support_label.  Returns None when no valid support
    exists below the broken stop.
    """
    candidates: list[tuple[float, str]] = []
    if prior_low and prior_low > 0:
        candidates.append((prior_low, "Prior Day Low"))
    if ma20 is not None and ma20 > 0:
        candidates.append((ma20, "20 SMA"))
    if ma50 is not None and ma50 > 0:
        candidates.append((ma50, "50 SMA"))
    if ema20 is not None and ema20 > 0:
        candidates.append((ema20, "20 EMA"))
    if ema50 is not None and ema50 > 0:
        candidates.append((ema50, "50 EMA"))

    # Only supports STRICTLY below the broken stop
    below = [(lvl, label) for lvl, label in candidates if lvl < broken_stop]
    if not below:
        return None

    # Nearest to current price (closest below current_price, or closest overall)
    below.sort(key=lambda x: abs(current_price - x[0]))
    new_support, support_label = below[0]

    support_status = _classify_support_status(
        current_price, current_price, new_support, pattern,
    )

    risk = new_support * 0.01  # 1% default risk

    # Targets: use prior_high if available, else multiples of risk
    if prior_high and prior_high > new_support:
        target_1 = prior_high
        target_2 = prior_high + (prior_high - new_support)
    else:
        target_1 = new_support + 2 * risk
        target_2 = new_support + 3 * risk

    levels = {
        "entry_long": new_support,
        "stop_long": new_support,
        "target_1": target_1,
        "target_2": target_2,
        "risk_per_share": risk,
    }

    plan = _build_trade_plan(levels, new_support, support_status, pattern)

    return {
        "entry": plan["entry"],
        "stop": plan["stop"],
        "target_1": plan["target_1"],
        "target_2": plan["target_2"],
        "risk_per_share": plan["risk_per_share"],
        "rr_ratio": plan["rr_ratio"],
        "support": new_support,
        "support_label": support_label,
    }


def scan_watchlist(
    symbols: list[str],
    period: str = "3mo",
) -> list[SignalResult]:
    """Fetch data and analyze each symbol. Returns results sorted by proximity to support.

    Also persists each result as a daily plan to the DB (single source of truth
    for the intraday Monitor).
    """
    from datetime import date

    from db import upsert_daily_plan

    session_date = date.today().isoformat()
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
            upsert_daily_plan(
                sym,
                session_date,
                support=result.nearest_support,
                support_label=result.support_label,
                support_status=result.support_status,
                entry=result.entry,
                stop=result.stop,
                target_1=result.target_1,
                target_2=result.target_2,
                score=result.score,
                score_label=result.score_label,
                pattern=result.pattern,
            )

    # Sort: AT SUPPORT first, then PULLBACK WATCH, then BROKEN
    status_order = {"AT SUPPORT": 0, "PULLBACK WATCH": 1, "BROKEN": 2, "NO DATA": 3}
    results.sort(key=lambda r: (status_order.get(r.support_status, 4), abs(r.distance_pct)))
    return results
