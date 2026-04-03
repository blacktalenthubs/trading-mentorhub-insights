"""Intraday data fetching — 5-minute bars and prior-day context.

Uses yfinance for both intraday and daily data.
"""

from __future__ import annotations

import pandas as pd
import pytz
import yfinance as yf

import logging

from analytics._cache import cache_data

from alert_config import (
    DAILY_DB_LOOKBACK_DAYS,
    DAILY_DB_MIN_DAYS_BETWEEN,
    DAILY_DB_MIN_RECOVERY_PCT,
    DAILY_DB_MIN_TOUCHES,
    DAILY_DB_SWING_LOW_CLUSTER_PCT,
    HOURLY_RESISTANCE_CLUSTER_PCT,
    SPY_MA_SUPPORT_PROXIMITY_PCT,
    SPY_SUPPORT_PROXIMITY_PCT,
    SPY_WEEKLY_PROXIMITY_PCT,
    SUPPORT_STRONG_HOLD_HOURS,
    SUPPORT_STRONG_RETEST_COUNT,
)

logger = logging.getLogger("intraday_data")

ET = pytz.timezone("US/Eastern")


def _compute_adx(daily_df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ADX from daily OHLC DataFrame using Wilder's smoothing."""
    high = daily_df["High"]
    low = daily_df["Low"]
    close = daily_df["Close"]

    plus_dm = high.diff()
    minus_dm = low.diff().abs()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # When +DM > -DM, -DM = 0 and vice versa
    mask = plus_dm > minus_dm
    minus_dm[mask] = 0
    plus_dm[~mask] = 0

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx


def compute_rvol(bars: pd.DataFrame, lookback_days: int = 10) -> float:
    """Compute time-normalized relative volume.

    Compares today's cumulative volume at this time of day
    vs the average cumulative volume at the same time over the past N days.
    Returns RVOL ratio (e.g., 1.5 = 50% above average).
    """
    if bars.empty or "Volume" not in bars.columns:
        return 1.0

    today_vol = bars["Volume"].sum()
    bars_count = len(bars)

    # Simple fallback: compare to average volume per bar x bar count
    avg_vol_per_bar = bars["Volume"].mean()
    if avg_vol_per_bar <= 0:
        return 1.0

    # For now, use simple volume ratio (time-normalized version needs historical bars)
    # This is already better than raw volume because it's per-bar averaged
    return today_vol / (avg_vol_per_bar * bars_count) if bars_count > 0 else 1.0


def _normalize_index_to_et(hist: pd.DataFrame) -> pd.DataFrame:
    """Convert yfinance index to ET, then strip timezone.

    yfinance returns UTC-aware timestamps for crypto and ET-aware for equities.
    This normalizes both to naive ET timestamps so date comparisons are
    consistent regardless of asset type.

    Follows the pattern from fetch_premarket_bars() (line 277-280).
    """
    if hist.empty:
        return hist
    if hist.index.tz is not None:
        hist.index = hist.index.tz_convert(ET).tz_localize(None)
    else:
        hist.index = hist.index.tz_localize("UTC").tz_convert(ET).tz_localize(None)
    return hist


def fetch_intraday(symbol: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """Fetch intraday bars for a symbol.

    Returns DataFrame with Open, High, Low, Close, Volume columns.
    Index is timezone-naive datetime. Returns empty DataFrame on failure.
    Drops the last bar if it is still forming (incomplete 5-min candle).
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist = _normalize_index_to_et(hist)
        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
        # Drop incomplete (in-progress) bar: if last bar started less than
        # 5 minutes ago, it hasn't closed yet.
        if len(df) > 1:
            from datetime import datetime, timedelta
            now = datetime.now()
            last_ts = df.index[-1].to_pydatetime()
            if now - last_ts < timedelta(minutes=5):
                df = df.iloc[:-1]
        return df
    except Exception:
        return pd.DataFrame()


def fetch_intraday_crypto(symbol: str, interval: str = "5m") -> pd.DataFrame:
    """Fetch intraday bars for crypto with UTC day boundary handling.

    Uses period="5d" and filters to today (ET) to avoid the near-empty
    bar problem at UTC midnight (7-8 PM ET) when period="1d" returns
    only the current UTC day's bars.

    Falls back to last 24h if today (ET) has fewer than 6 bars.
    """
    bars = fetch_intraday(symbol, period="5d", interval=interval)
    if bars.empty:
        return bars

    # After _normalize_index_to_et, index is naive ET. Filter to today (ET).
    today = pd.Timestamp.now().normalize()
    today_bars = bars[bars.index.normalize() == today]
    if len(today_bars) >= 6:
        return today_bars

    # Fallback: return last 24h of bars (covers UTC midnight transition)
    cutoff = pd.Timestamp.now() - pd.Timedelta(hours=24)
    fallback = bars[bars.index >= cutoff]
    return fallback if not fallback.empty else bars.tail(6)


@cache_data(ttl=900, show_spinner=False)
def fetch_hourly_bars(symbol: str, period: str = "5d") -> pd.DataFrame:
    """Fetch hourly bars for a symbol (cached 15 min).

    Thin wrapper around fetch_intraday with 1h interval.
    Returns DataFrame with Open, High, Low, Close, Volume columns.
    """
    return fetch_intraday(symbol, period=period, interval="1h")


# ---------------------------------------------------------------------------
# Overnight futures
# ---------------------------------------------------------------------------

FUTURES_EQUITY_MAP = {"ES=F": "SPY", "NQ=F": "QQQ"}


def fetch_overnight_futures(
    symbol: str = "ES=F",
    period: str = "5d",
    interval: str = "1h",
) -> pd.DataFrame:
    """Fetch overnight futures bars from prior equity close (4 PM ET) to now.

    Futures trade Sunday 6 PM - Friday 5 PM ET with a daily break 5-6 PM ET.
    Filters to bars AFTER the most recent 4 PM ET equity close.

    Returns DataFrame with Open, High, Low, Close, Volume columns.
    Index is timezone-naive ET datetime. Returns empty DataFrame on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist = _normalize_index_to_et(hist)
        df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        # Find the most recent 4 PM ET cutoff (prior equity close)
        now_et = pd.Timestamp.now()
        today_4pm = now_et.normalize() + pd.Timedelta(hours=16)

        if now_et >= today_4pm:
            cutoff = today_4pm
        else:
            cutoff = today_4pm - pd.Timedelta(days=1)
            # Skip weekends: if cutoff lands on Sat/Sun, go back to Friday
            while cutoff.weekday() >= 5:
                cutoff -= pd.Timedelta(days=1)

        overnight = df[df.index >= cutoff]
        return overnight
    except Exception:
        logger.warning("Failed to fetch overnight futures for %s", symbol)
        return pd.DataFrame()


def compute_overnight_context(
    es_bars: pd.DataFrame,
    nq_bars: pd.DataFrame,
    spy_prior_close: float,
    qqq_prior_close: float,
) -> dict | None:
    """Compute overnight futures context for the premarket brief.

    Returns dict with per-futures metrics and overall overnight_bias,
    or None if no data available.
    """
    if es_bars.empty and nq_bars.empty:
        return None

    result = {}

    for bars, future_sym, equity_sym, equity_close in [
        (es_bars, "ES=F", "SPY", spy_prior_close),
        (nq_bars, "NQ=F", "QQQ", qqq_prior_close),
    ]:
        if bars.empty or equity_close <= 0:
            result[future_sym] = None
            continue

        on_high = bars["High"].max()
        on_low = bars["Low"].min()
        on_last = bars["Close"].iloc[-1]
        on_open = bars["Open"].iloc[0]
        on_change_pct = (on_last - on_open) / on_open * 100 if on_open > 0 else 0.0

        # Projected gap: futures % change applies to equity
        projected_gap_pct = on_change_pct

        # Overnight VWAP (volume-weighted)
        on_vwap = None
        if "Volume" in bars.columns and bars["Volume"].sum() > 0:
            typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
            cum_vol = bars["Volume"].cumsum()
            cum_tp_vol = (typical * bars["Volume"]).cumsum()
            vwap_series = cum_tp_vol / cum_vol
            on_vwap = round(float(vwap_series.iloc[-1]), 2)

        if on_change_pct > 0.3:
            on_trend = "BULLISH"
        elif on_change_pct < -0.3:
            on_trend = "BEARISH"
        else:
            on_trend = "FLAT"

        result[future_sym] = {
            "future_symbol": future_sym,
            "equity_symbol": equity_sym,
            "on_high": round(float(on_high), 2),
            "on_low": round(float(on_low), 2),
            "on_last": round(float(on_last), 2),
            "on_open": round(float(on_open), 2),
            "on_change_pct": round(on_change_pct, 2),
            "on_vwap": on_vwap,
            "on_trend": on_trend,
            "projected_gap_pct": round(projected_gap_pct, 2),
            "equity_prior_close": round(equity_close, 2),
            "bar_count": len(bars),
        }

    # Overall overnight bias
    es = result.get("ES=F")
    nq = result.get("NQ=F")
    if es and nq:
        avg_change = (es["on_change_pct"] + nq["on_change_pct"]) / 2
        if avg_change > 0.3:
            result["overnight_bias"] = "BULLISH"
        elif avg_change < -0.3:
            result["overnight_bias"] = "BEARISH"
        else:
            result["overnight_bias"] = "FLAT"
    elif es:
        result["overnight_bias"] = es["on_trend"]
    elif nq:
        result["overnight_bias"] = nq["on_trend"]
    else:
        result["overnight_bias"] = "UNKNOWN"

    return result


def detect_hourly_resistance(
    bars_1h: pd.DataFrame,
    cluster_pct: float = HOURLY_RESISTANCE_CLUSTER_PCT,
) -> list[float]:
    """Find hourly swing high resistance levels from multi-day 1h bars.

    Algorithm:
    1. Find swing highs: bar whose High > both neighbors' High
    2. Filter out broken levels: if a later bar closed above the swing high,
       that level has been breached and is no longer resistance
    3. Cluster nearby levels within cluster_pct — keep the max in each cluster
    4. Return sorted ascending list of resistance levels

    Mirrors detect_intraday_supports() pattern.
    """
    if bars_1h.empty or len(bars_1h) < 3:
        return []

    # Step 1: swing high detection (neighbor comparison) — track index
    swing_highs: list[tuple[int, float]] = []
    for i in range(1, len(bars_1h) - 1):
        if (bars_1h["High"].iloc[i] > bars_1h["High"].iloc[i - 1]
                and bars_1h["High"].iloc[i] > bars_1h["High"].iloc[i + 1]):
            swing_highs.append((i, float(bars_1h["High"].iloc[i])))

    if not swing_highs:
        return []

    # Step 2: filter out broken levels — if any later bar closed above
    # the swing high, that level was breached and is no longer resistance
    unbroken: list[float] = []
    for idx, level in swing_highs:
        broken = False
        for j in range(idx + 1, len(bars_1h)):
            if bars_1h["Close"].iloc[j] > level:
                broken = True
                break
        if not broken:
            unbroken.append(level)

    if not unbroken:
        return []

    # Step 3: cluster within cluster_pct, keep max per cluster
    unbroken.sort()
    clusters: list[list[float]] = [[unbroken[0]]]
    for level in unbroken[1:]:
        if (level - clusters[-1][0]) / clusters[-1][0] <= cluster_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    # Step 4: return max of each cluster, sorted ascending
    return sorted(max(c) for c in clusters)


def detect_hourly_support(
    bars_1h: pd.DataFrame,
    cluster_pct: float = HOURLY_RESISTANCE_CLUSTER_PCT,
) -> list[float]:
    """Find hourly swing low support levels from multi-day 1h bars.

    Mirrors detect_hourly_resistance() but uses swing lows.
    """
    if bars_1h.empty or len(bars_1h) < 3:
        return []

    swing_lows: list[float] = []
    for i in range(1, len(bars_1h) - 1):
        if (bars_1h["Low"].iloc[i] < bars_1h["Low"].iloc[i - 1]
                and bars_1h["Low"].iloc[i] < bars_1h["Low"].iloc[i + 1]):
            swing_lows.append(float(bars_1h["Low"].iloc[i]))

    if not swing_lows:
        return []

    swing_lows.sort()
    clusters: list[list[float]] = [[swing_lows[0]]]
    for level in swing_lows[1:]:
        if (level - clusters[-1][0]) / clusters[-1][0] <= cluster_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    return sorted(min(c) for c in clusters)


def detect_daily_double_bottoms(
    hist: pd.DataFrame,
    lookback_days: int = DAILY_DB_LOOKBACK_DAYS,
    cluster_pct: float = DAILY_DB_SWING_LOW_CLUSTER_PCT,
    min_touches: int = DAILY_DB_MIN_TOUCHES,
    min_days_between: int = DAILY_DB_MIN_DAYS_BETWEEN,
    min_recovery_pct: float = DAILY_DB_MIN_RECOVERY_PCT,
) -> list[dict]:
    """Find multi-day double bottom zones from daily OHLCV bars.

    Scans the last ``lookback_days`` completed daily bars for support zones
    that have been tested multiple times.  The algorithm considers **all**
    daily bar lows (not only strict swing lows) because the double-bottom
    pattern on a daily chart often manifests as repeated tests of the same
    zone without each individual bar qualifying as a classic swing low.

    Only bars whose Low is in the lower half of the lookback range are
    considered candidates — this filters out trivial dips in an uptrend.

    A cluster qualifies as a double bottom when:

    * it has ``min_touches`` or more,
    * the first and last touches are at least ``min_days_between`` bars apart,
    * there is a meaningful recovery (``min_recovery_pct``) between them, and
    * lows are not descending (last touch is not significantly below first).

    Args:
        hist: Daily OHLCV DataFrame **already trimmed to completed bars**
              (caller must exclude today's partial bar).
        lookback_days: How many completed daily bars to scan.
        cluster_pct: Max distance (%) to group nearby lows into one zone.
        min_touches: Minimum touches for a valid double bottom.
        min_days_between: Minimum bar gap between first and last touch.
        min_recovery_pct: Minimum % bounce above zone low between touches.

    Returns:
        List of dicts sorted ascending by level::

            [{"level": float,           # zone low (min of cluster)
              "touch_count": int,        # number of bar-low touches
              "first_touch_idx": int,    # bar index of first touch
              "last_touch_idx": int,     # bar index of last touch
              "zone_high": float}]       # zone high (max of cluster)
    """
    if hist.empty or len(hist) < 5:
        return []

    bars = hist.tail(lookback_days).reset_index(drop=True)
    if len(bars) < 5:
        return []

    # Step 1: Collect candidate lows — bars in the lower 75% of the range.
    # This filters out trivial dips near the highs (top quartile) while
    # catching the repeated zone tests that define a double bottom.
    # We use 75% because volatile assets (crypto) can have wide ranges
    # from a single crash bar that makes the range enormous.
    period_high = float(bars["High"].max())
    period_low = float(bars["Low"].min())
    period_range = period_high - period_low
    if period_range <= 0:
        return []
    cutoff = period_low + period_range * 0.75

    candidate_lows: list[tuple[int, float]] = []  # (bar_index, low)
    for i in range(len(bars)):
        bar_low = float(bars["Low"].iloc[i])
        if bar_low <= cutoff:
            candidate_lows.append((i, bar_low))

    if len(candidate_lows) < min_touches:
        return []

    # Step 2: Sort by price and cluster within cluster_pct
    candidate_lows.sort(key=lambda x: x[1])
    clusters: list[list[tuple[int, float]]] = [[candidate_lows[0]]]
    for idx, level in candidate_lows[1:]:
        cluster_base = clusters[-1][0][1]  # first (lowest) in cluster
        if (level - cluster_base) / cluster_base <= cluster_pct:
            clusters[-1].append((idx, level))
        else:
            clusters.append([(idx, level)])

    # Step 3: Filter clusters that qualify as double bottoms
    results: list[dict] = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue

        indices = [c[0] for c in cluster]
        levels = [c[1] for c in cluster]
        first_idx = min(indices)
        last_idx = max(indices)

        # Must be separate days
        if last_idx - first_idx < min_days_between:
            continue

        zone_low = min(levels)
        zone_high = max(levels)

        # Reject descending lows — last touch significantly below first touch
        first_touch_low = next(lv for ix, lv in cluster if ix == first_idx)
        last_touch_low = next(lv for ix, lv in cluster if ix == last_idx)
        if last_touch_low < first_touch_low * (1 - cluster_pct):
            continue

        # Check for recovery between touches: at least one bar between
        # first and last touch must have its Close above zone_low * (1 + recovery).
        # We use Close (not Low) because V-shaped recoveries have bars
        # whose wicks dip below the zone even as the trend recovers.
        # We measure from zone_low (not zone_high) because what matters is
        # that price bounced away from support, not that it exceeded the
        # highest touch.
        recovery_threshold = zone_low * (1 + min_recovery_pct)
        has_recovery = False
        for i in range(first_idx + 1, last_idx):
            if bars["Close"].iloc[i] > recovery_threshold:
                has_recovery = True
                break

        if not has_recovery:
            continue

        results.append({
            "level": round(zone_low, 2),
            "touch_count": len(cluster),
            "first_touch_idx": first_idx,
            "last_touch_idx": last_idx,
            "zone_high": round(zone_high, 2),
        })

    results.sort(key=lambda x: x["level"])
    return results


def _safe_daily_double_bottoms(
    hist: pd.DataFrame, market_open: bool,
) -> list[dict]:
    """Wrapper that silences errors so fetch_prior_day never breaks.

    Includes today's partial bar so that intraday wicks into a prior
    daily low zone count as the second touch (real-time detection).
    """
    try:
        return detect_daily_double_bottoms(hist)
    except Exception:
        return []


def _compute_daily_trend(hist: pd.DataFrame, market_open: bool) -> dict:
    """Compute daily trend structure from swing highs/lows.

    Looks at last 10 completed daily bars to identify:
    - Higher highs / lower highs
    - Higher lows / lower lows
    - Overall trend bias: bullish / bearish / neutral
    - Key structure: ascending triangle, descending triangle, channel

    Returns dict with trend, structure, and recent swing points.
    """
    result = {
        "bias": "neutral",
        "structure": "none",
        "higher_highs": False,
        "lower_highs": False,
        "higher_lows": False,
        "lower_lows": False,
        "recent_swing_high": 0.0,
        "recent_swing_low": 0.0,
    }
    try:
        completed = hist.iloc[:-1] if market_open else hist
        if len(completed) < 10:
            return result

        # Use last 10 daily bars
        recent = completed.iloc[-10:]

        # Find swing highs (bar higher than both neighbors)
        swing_highs = []
        swing_lows = []
        for i in range(1, len(recent) - 1):
            if (recent["High"].iloc[i] > recent["High"].iloc[i - 1]
                    and recent["High"].iloc[i] > recent["High"].iloc[i + 1]):
                swing_highs.append(float(recent["High"].iloc[i]))
            if (recent["Low"].iloc[i] < recent["Low"].iloc[i - 1]
                    and recent["Low"].iloc[i] < recent["Low"].iloc[i + 1]):
                swing_lows.append(float(recent["Low"].iloc[i]))

        # Need at least 2 swings to determine trend
        if len(swing_highs) >= 2:
            result["higher_highs"] = swing_highs[-1] > swing_highs[-2]
            result["lower_highs"] = swing_highs[-1] < swing_highs[-2]
            result["recent_swing_high"] = round(swing_highs[-1], 2)

        if len(swing_lows) >= 2:
            result["higher_lows"] = swing_lows[-1] > swing_lows[-2]
            result["lower_lows"] = swing_lows[-1] < swing_lows[-2]
            result["recent_swing_low"] = round(swing_lows[-1], 2)

        # Determine bias
        if result["higher_highs"] and result["higher_lows"]:
            result["bias"] = "bullish"
        elif result["lower_highs"] and result["lower_lows"]:
            result["bias"] = "bearish"
        elif result["lower_highs"] and result["higher_lows"]:
            result["bias"] = "neutral"
            result["structure"] = "contracting"  # triangle / wedge
        elif result["higher_highs"] and result["lower_lows"]:
            result["bias"] = "neutral"
            result["structure"] = "expanding"  # broadening

        # Detect descending triangle: lower highs + flat lows
        if result["lower_highs"] and not result["lower_lows"] and len(swing_lows) >= 2:
            low_range = abs(swing_lows[-1] - swing_lows[-2])
            avg_low = (swing_lows[-1] + swing_lows[-2]) / 2
            if avg_low > 0 and low_range / avg_low < 0.01:  # lows within 1%
                result["structure"] = "descending_triangle"
                result["bias"] = "bearish"

        # Detect ascending triangle: higher lows + flat highs
        if result["higher_lows"] and not result["higher_highs"] and len(swing_highs) >= 2:
            high_range = abs(swing_highs[-1] - swing_highs[-2])
            avg_high = (swing_highs[-1] + swing_highs[-2]) / 2
            if avg_high > 0 and high_range / avg_high < 0.01:  # highs within 1%
                result["structure"] = "ascending_triangle"
                result["bias"] = "bullish"

        # EMA trend confirmation (20 EMA slope)
        if "EMA20" in completed.columns and len(completed) >= 5:
            ema20_now = completed["EMA20"].iloc[-1]
            ema20_5ago = completed["EMA20"].iloc[-5]
            if pd.notna(ema20_now) and pd.notna(ema20_5ago) and ema20_5ago > 0:
                ema_slope = (ema20_now - ema20_5ago) / ema20_5ago
                if ema_slope < -0.01:  # EMA falling > 1%
                    if result["bias"] == "neutral":
                        result["bias"] = "bearish"
                elif ema_slope > 0.01:  # EMA rising > 1%
                    if result["bias"] == "neutral":
                        result["bias"] = "bullish"

    except Exception:
        pass
    return result


def fetch_prior_day(symbol: str, is_crypto: bool = False) -> dict | None:
    """Fetch the PRIOR COMPLETED trading day's data.

    During market hours the last bar from yfinance is today's partial data,
    so we use iloc[-2] (yesterday) and iloc[-3] (day before).
    After close the last bar is the completed day, so iloc[-1] and iloc[-2].

    For crypto (is_crypto=True): yfinance daily bars are aggregated on UTC
    midnight boundaries. We keep UTC dates and compare against UTC "today"
    to avoid an off-by-one error from ET conversion.

    Returns dict with keys: open, high, low, close, volume, ma20, ma50,
    ma100, ma200, pattern, direction, parent_high, parent_low.
    Returns None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")
        if hist.empty or len(hist) < 3:
            return None

        if is_crypto:
            # Crypto daily bars aggregate on UTC midnight boundaries.
            # Keep UTC dates (don't convert to ET) for correct day selection.
            if hist.index.tz is not None:
                hist.index = hist.index.tz_convert("UTC").tz_localize(None)
        else:
            hist = _normalize_index_to_et(hist)

        hist = hist[["Open", "High", "Low", "Close", "Volume"]].copy()

        # Compute MAs on full history
        hist["MA20"] = hist["Close"].rolling(window=20).mean()
        hist["MA50"] = hist["Close"].rolling(window=50).mean()
        hist["MA100"] = hist["Close"].rolling(window=100).mean()
        hist["MA200"] = hist["Close"].rolling(window=200).mean()

        # Compute EMAs on full history
        hist["EMA5"] = hist["Close"].ewm(span=5, adjust=False).mean()
        hist["EMA10"] = hist["Close"].ewm(span=10, adjust=False).mean()
        hist["EMA20"] = hist["Close"].ewm(span=20, adjust=False).mean()
        hist["EMA50"] = hist["Close"].ewm(span=50, adjust=False).mean()
        hist["EMA100"] = hist["Close"].ewm(span=100, adjust=False).mean()
        hist["EMA200"] = hist["Close"].ewm(span=200, adjust=False).mean()

        # Date-aware selection: if last bar is today, it's partial
        if is_crypto:
            # Use naive UTC "today" to match the naive UTC index
            from datetime import datetime, timezone
            today = pd.Timestamp(
                datetime.now(timezone.utc).replace(tzinfo=None)
            ).normalize()
        else:
            today = pd.Timestamp.now().normalize()
        last_bar_date = hist.index[-1].normalize()

        if last_bar_date >= today:
            # Market is open — last bar is today's partial data
            if len(hist) < 4:
                return None
            last = hist.iloc[-2]  # yesterday (prior completed day)
            prev = hist.iloc[-3]  # day before yesterday
        else:
            # Market closed — last bar is the completed day
            last = hist.iloc[-1]
            prev = hist.iloc[-2]

        # ── Crypto weekend gap fix ──────────────────────────────────────
        # yfinance sometimes skips crypto daily bars on weekends.
        # If the "prior day" is >1 calendar day before today, fill from
        # hourly bars to get the actual prior day OHLC.
        if is_crypto:
            _prior_date = last.name.normalize() if hasattr(last.name, 'normalize') else pd.Timestamp(last.name).normalize()
            _gap_days = (today - _prior_date).days
            if _gap_days > 1:
                try:
                    _h_ticker = yf.Ticker(symbol)
                    _h_bars = _h_ticker.history(period="5d", interval="1h")
                    if not _h_bars.empty:
                        if _h_bars.index.tz is not None:
                            _h_bars.index = _h_bars.index.tz_convert("UTC").tz_localize(None)
                        # Group by UTC date, find yesterday
                        _yesterday = today - pd.Timedelta(days=1)
                        _yday_bars = _h_bars[_h_bars.index.normalize() == _yesterday]
                        if len(_yday_bars) >= 6:
                            # Override prior day OHLCV from hourly aggregation
                            last = pd.Series({
                                "Open": _yday_bars["Open"].iloc[0],
                                "High": _yday_bars["High"].max(),
                                "Low": _yday_bars["Low"].min(),
                                "Close": _yday_bars["Close"].iloc[-1],
                                "Volume": _yday_bars["Volume"].sum(),
                                # Carry forward MA values (computed on daily)
                                **{col: last[col] for col in last.index if col not in ("Open", "High", "Low", "Close", "Volume")},
                            }, name=_yesterday)
                            logger.info(
                                "Crypto weekend fix: %s prior day filled from hourly "
                                "(date=%s, H=%.2f, L=%.2f)",
                                symbol, _yesterday.strftime("%Y-%m-%d"),
                                last["High"], last["Low"],
                            )
                except Exception as _e:
                    logger.warning("Crypto weekend fix failed for %s: %s", symbol, _e)

        # Weekly resampling: prior week high/low from existing hist
        prior_week_high = None
        prior_week_low = None
        try:
            weekly = hist[["High", "Low"]].resample("W-FRI").agg({
                "High": "max", "Low": "min",
            }).dropna()
            if len(weekly) >= 2:
                last_weekly_date = weekly.index[-1].normalize()
                if last_bar_date <= last_weekly_date:
                    prior_week = weekly.iloc[-2]  # current week partial
                else:
                    prior_week = weekly.iloc[-1]  # current week ended
                prior_week_high = prior_week["High"]
                prior_week_low = prior_week["Low"]
        except Exception:
            pass

        # Monthly resampling: prior month high/low + monthly EMAs from existing hist
        prior_month_high = None
        prior_month_low = None
        monthly_ema8 = None
        monthly_ema20 = None
        try:
            monthly = hist[["High", "Low", "Close"]].resample("MS").agg({
                "High": "max", "Low": "min", "Close": "last",
            }).dropna()
            if len(monthly) >= 2:
                last_monthly_date = monthly.index[-1].normalize()
                if last_bar_date >= last_monthly_date:
                    prior_month = monthly.iloc[-2]  # current month partial
                else:
                    prior_month = monthly.iloc[-1]
                prior_month_high = prior_month["High"]
                prior_month_low = prior_month["Low"]

                # Monthly EMAs — use last completed month's values
                # (exclude current partial month)
                completed_monthly = monthly.iloc[:-1] if last_bar_date >= last_monthly_date else monthly
                if len(completed_monthly) >= 8:
                    m_ema8 = completed_monthly["Close"].ewm(span=8, adjust=False).mean()
                    monthly_ema8 = float(m_ema8.iloc[-1])
                if len(completed_monthly) >= 20:
                    m_ema20 = completed_monthly["Close"].ewm(span=20, adjust=False).mean()
                    monthly_ema20 = float(m_ema20.iloc[-1])
        except Exception:
            pass

        ma20 = last["MA20"] if pd.notna(last["MA20"]) else None
        ma50 = last["MA50"] if pd.notna(last["MA50"]) else None
        ma100 = last["MA100"] if pd.notna(last["MA100"]) else None
        ma200 = last["MA200"] if pd.notna(last["MA200"]) else None
        ema5 = last["EMA5"] if pd.notna(last["EMA5"]) else None
        ema5_prev = prev["EMA5"] if pd.notna(prev["EMA5"]) else None
        ema10 = last["EMA10"] if pd.notna(last["EMA10"]) else None
        ema10_prev = prev["EMA10"] if pd.notna(prev["EMA10"]) else None
        ema20 = last["EMA20"] if pd.notna(last["EMA20"]) else None
        ema20_prev = prev["EMA20"] if pd.notna(prev["EMA20"]) else None
        ema50 = last["EMA50"] if pd.notna(last["EMA50"]) else None
        ema100 = last["EMA100"] if pd.notna(last["EMA100"]) else None
        ema200 = last["EMA200"] if pd.notna(last["EMA200"]) else None

        sym_rsi14 = compute_rsi_wilder(hist["Close"], period=14)

        # RSI series for crossover detection (prev, today)
        rsi_vals = compute_rsi_series(hist["Close"], period=14, lookback=2)
        rsi14_prev = rsi_vals[0] if len(rsi_vals) >= 2 else None

        # ADX(14) for trend strength — used by ADX gate in evaluate_rules()
        adx_series = _compute_adx(hist)
        _adx14 = float(adx_series.iloc[-1]) if len(adx_series) > 0 and pd.notna(adx_series.iloc[-1]) else None
        _adx14_prev = float(adx_series.iloc[-2]) if len(adx_series) > 1 and pd.notna(adx_series.iloc[-2]) else None

        # Classify the prior day using market_data.classify_day
        from analytics.market_data import classify_day
        pattern, direction = classify_day(last, prev)

        # Check if prior day was an inside day
        is_inside = last["High"] <= prev["High"] and last["Low"] >= prev["Low"]

        return {
            "open": last["Open"],
            "high": last["High"],
            "low": last["Low"],
            "close": last["Close"],
            "volume": last["Volume"],
            "ma20": ma20,
            "ma50": ma50,
            "ma100": ma100,
            "ma200": ma200,
            "ema5": ema5,
            "ema5_prev": ema5_prev,
            "ema10": ema10,
            "ema10_prev": ema10_prev,
            "ema20": ema20,
            "ema20_prev": ema20_prev,
            "ema50": ema50,
            "ema100": ema100,
            "ema200": ema200,
            "pattern": pattern,
            "direction": direction,
            "is_inside": is_inside,
            "parent_high": prev["High"],
            "parent_low": prev["Low"],
            "parent_range": prev["High"] - prev["Low"],
            "prev_close": prev["Close"],
            "prior_week_high": prior_week_high,
            "prior_week_low": prior_week_low,
            "prior_month_high": prior_month_high,
            "prior_month_low": prior_month_low,
            "monthly_ema8": monthly_ema8,
            "monthly_ema20": monthly_ema20,
            "rsi14": sym_rsi14,
            "rsi14_prev": rsi14_prev,
            "adx14": _adx14,
            "adx14_prev": _adx14_prev,
            "daily_double_bottoms": _safe_daily_double_bottoms(
                hist, last_bar_date >= today
            ),
            "daily_trend": _compute_daily_trend(hist, last_bar_date >= today),
        }
    except Exception:
        return None


@cache_data(ttl=120, show_spinner=False)
def fetch_premarket_bars(symbol: str, interval: str = "5m") -> pd.DataFrame:
    """Fetch today's pre-market bars (4:00-9:29 AM ET).

    Uses yfinance with prepost=True to get extended-hours data.
    Returns DataFrame with OHLC columns (Volume excluded — always 0 in PM).
    Returns empty DataFrame on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d", interval=interval, prepost=True)
        if hist.empty:
            return pd.DataFrame()

        # Ensure timezone-aware index in ET
        if hist.index.tz is None:
            hist.index = hist.index.tz_localize("UTC").tz_convert(ET)
        else:
            hist.index = hist.index.tz_convert(ET)

        # Filter to today's date, hours 4:00-9:29 ET only
        today = pd.Timestamp.now(tz=ET).normalize()
        today_bars = hist[hist.index.normalize() == today]
        pm_bars = today_bars[
            (today_bars.index.hour >= 4)
            & ((today_bars.index.hour < 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute < 30)))
        ]

        if pm_bars.empty:
            return pd.DataFrame()

        # Strip timezone for consistency with rest of codebase
        pm_bars = pm_bars.copy()
        pm_bars.index = pm_bars.index.tz_localize(None)
        return pm_bars[["Open", "High", "Low", "Close"]].copy()
    except Exception:
        return pd.DataFrame()


def compute_premarket_brief(symbol: str, pm_bars: pd.DataFrame, prior_day: dict) -> dict | None:
    """Compute pre-market brief metrics from PM bars and prior day data.

    Args:
        symbol: Ticker symbol.
        pm_bars: Pre-market OHLC bars from fetch_premarket_bars().
        prior_day: Dict from fetch_prior_day() with open/high/low/close/ma20/ma50.

    Returns dict with PM metrics, priority score, and flags. None on failure.
    """
    if pm_bars.empty or prior_day is None:
        return None

    prior_close = prior_day["close"]
    if prior_close <= 0:
        return None

    pm_high = pm_bars["High"].max()
    pm_low = pm_bars["Low"].min()
    pm_last = pm_bars["Close"].iloc[-1]
    pm_open = pm_bars["Open"].iloc[0]

    pm_change_pct = round((pm_last - prior_close) / prior_close * 100, 2)

    # Gap: prior close to first PM bar open
    gap_info = classify_gap(pm_open, prior_close, prior_day.get("parent_range", 0))
    gap_pct = gap_info["gap_pct"]
    gap_type = gap_info["type"]

    # Level tests
    above_prior_high = bool(pm_high > prior_day["high"])
    below_prior_low = bool(pm_low < prior_day["low"])

    # MA proximity (within 0.5%)
    ma20 = prior_day.get("ma20")
    ma50 = prior_day.get("ma50")
    near_ma20 = bool(ma20 and ma20 > 0 and abs(pm_last - ma20) / ma20 <= 0.005)
    near_ma50 = bool(ma50 and ma50 > 0 and abs(pm_last - ma50) / ma50 <= 0.005)

    # PM range
    pm_range_pct = round((pm_high - pm_low) / pm_low * 100, 2) if pm_low > 0 else 0.0

    # Priority score (0-100)
    score = 0
    abs_gap = abs(gap_pct)
    if abs_gap > 1.0:
        score += 30
    elif abs_gap >= 0.5:
        score += 20
    elif abs_gap >= 0.3:
        score += 10
    if above_prior_high or below_prior_low:
        score += 20
    if near_ma20 or near_ma50:
        score += 15
    if pm_range_pct > 1.0:
        score += 10
    if gap_type != "flat":
        score += 5
    score = min(score, 100)

    # Priority label
    if score >= 50:
        priority_label = "HIGH"
    elif score >= 25:
        priority_label = "MEDIUM"
    else:
        priority_label = "LOW"

    # Flags
    flags = []
    if gap_type == "gap_up":
        flags.append(f"GAP UP +{abs_gap:.1f}%")
    elif gap_type == "gap_down":
        flags.append(f"GAP DOWN -{abs_gap:.1f}%")
    if above_prior_high:
        flags.append("TESTING PRIOR HIGH")
    if below_prior_low:
        flags.append("TESTING PRIOR LOW")
    if near_ma20:
        flags.append("NEAR 20MA")
    if near_ma50:
        flags.append("NEAR 50MA")
    if pm_range_pct > 1.0:
        flags.append(f"WIDE RANGE {pm_range_pct:.1f}%")

    return {
        "symbol": symbol,
        "pm_high": round(pm_high, 2),
        "pm_low": round(pm_low, 2),
        "pm_last": round(pm_last, 2),
        "pm_change_pct": pm_change_pct,
        "gap_pct": gap_pct,
        "gap_type": gap_type,
        "above_prior_high": above_prior_high,
        "below_prior_low": below_prior_low,
        "near_ma20": near_ma20,
        "near_ma50": near_ma50,
        "pm_range_pct": pm_range_pct,
        "priority_score": score,
        "priority_label": priority_label,
        "flags": flags,
    }


def _compute_spy_bounce_rate(hist: pd.DataFrame) -> dict:
    """Compute how often SPY bounces at the prior day's low.

    Loops through daily bars, checks if each day's Low tested the prior day's
    Low (within 0.05%, same threshold as spy_patterns.classify_day()).
    Classifies as bounce (Close > prior_low) or break.

    Returns {"bounce_rate": float, "sample_size": int}.
    Default 0.5 if fewer than 5 tested days.
    """
    if len(hist) < 10:
        return {"bounce_rate": 0.5, "sample_size": 0}

    bounces = 0
    breaks = 0
    for i in range(1, len(hist)):
        prior_low = hist["Low"].iloc[i - 1]
        if prior_low <= 0:
            continue
        threshold = prior_low * (0.05 / 100)  # 0.05% of prior low
        day_low = hist["Low"].iloc[i]
        day_close = hist["Close"].iloc[i]

        # Did this day test the prior day's low?
        if day_low <= prior_low + threshold:
            if day_close > prior_low:
                bounces += 1
            else:
                breaks += 1

    total = bounces + breaks
    if total < 5:
        return {"bounce_rate": 0.5, "sample_size": total}

    return {"bounce_rate": round(bounces / total, 2), "sample_size": total}


def compute_rsi_wilder(closes: pd.Series, period: int = 14) -> float | None:
    """Compute RSI using Wilder's smoothing (ewm with alpha=1/period).

    Returns RSI value in [0, 100], or None if insufficient data.
    """
    if closes is None or len(closes) < period + 1:
        return None

    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    last_avg_gain = avg_gain.iloc[-1]
    last_avg_loss = avg_loss.iloc[-1]

    if last_avg_loss == 0:
        return 100.0 if last_avg_gain > 0 else 50.0

    rs = last_avg_gain / last_avg_loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi, 2)


def compute_rsi_series(
    closes: pd.Series, period: int = 14, lookback: int = 2
) -> list[float]:
    """Return the last *lookback* RSI values for crossover detection.

    Same Wilder's EWM logic as ``compute_rsi_wilder`` but returns a short
    list instead of a single scalar.  Returns empty list on insufficient data.
    """
    if len(closes) < period + 1:
        return []

    delta = closes.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.dropna()

    if rsi_series.empty:
        return []

    return [round(v, 2) for v in rsi_series.iloc[-lookback:].tolist()]


@cache_data(ttl=300)
def get_spy_context() -> dict:
    """Fetch SPY trend data for market context (cached 5 min).

    Returns dict with trend, close, ma20, and intraday_change_pct.
    """
    _default = {
        "trend": "neutral", "close": 0.0, "ma20": 0.0,
        "ma5": 0.0, "ma50": 0.0, "regime": "CHOPPY",
        "intraday_change_pct": 0.0, "spy_bouncing": False, "spy_intraday_low": 0.0,
        "spy_at_support": False, "spy_at_resistance": False,
        "spy_level_label": "", "spy_support_bounce_rate": 0.5,
        "spy_rsi14": None, "spy_ema20": 0.0, "spy_ema50": 0.0,
        "spy_ema_spread_pct": 0.0, "spy_at_ma_support": None,
        "spy_ema_regime": "CHOPPY",
    }
    try:
        spy = yf.Ticker("SPY")
        hist = spy.history(period="1y")
        if hist.empty or len(hist) < 20:
            return _default
        ma5 = hist["Close"].rolling(5).mean().iloc[-1]
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        ma50_raw = hist["Close"].rolling(50).mean().iloc[-1]
        ma50 = ma50_raw if pd.notna(ma50_raw) else ma20
        close = hist["Close"].iloc[-1]
        trend = "bullish" if close > ma20 else "bearish"
        regime = classify_market_regime(close, ma5, ma20, ma50)

        # RSI14 on daily closes (Wilder's smoothing)
        spy_rsi14 = compute_rsi_wilder(hist["Close"], period=14)

        # EMA20/50 on daily closes
        spy_ema20 = hist["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        spy_ema50_raw = hist["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
        spy_ema50 = spy_ema50_raw if pd.notna(spy_ema50_raw) else spy_ema20

        # EMA spread: (ema20 - ema50) / price * 100
        spy_ema_spread_pct = (spy_ema20 - spy_ema50) / close * 100 if close > 0 else 0.0

        # SPY MA-level detection: is SPY near its own 50/100/200 SMA?
        spy_at_ma_support = None
        ma100_val = hist["Close"].rolling(100).mean().iloc[-1] if len(hist) >= 100 else None
        ma200_val = hist["Close"].rolling(200).mean().iloc[-1] if len(hist) >= 200 else None
        for ma_val, ma_label in [
            (ma50, "50MA"), (ma100_val, "100MA"), (ma200_val, "200MA"),
        ]:
            if ma_val and pd.notna(ma_val) and ma_val > 0:
                if abs(close - ma_val) / ma_val <= SPY_MA_SUPPORT_PROXIMITY_PCT:
                    spy_at_ma_support = ma_label
                    break

        # EMA-based regime (observational — log when it disagrees with SMA regime)
        spy_ema_regime = classify_market_regime(close, ma5, spy_ema20, spy_ema50)
        if spy_ema_regime != regime:
            logger.info(
                "SPY regime divergence: SMA=%s vs EMA=%s (SMA50=%.2f, EMA50=%.2f)",
                regime, spy_ema_regime, ma50, spy_ema50,
            )

        # Compute SPY intraday % change and bounce detection from today's bars
        intraday_change_pct = 0.0
        spy_bouncing = False
        spy_intraday_low = 0.0
        try:
            spy_intra = spy.history(period="1d", interval="5m")
            if not spy_intra.empty and len(spy_intra) >= 2:
                spy_open = spy_intra["Open"].iloc[0]
                spy_current = spy_intra["Close"].iloc[-1]
                if spy_open > 0:
                    intraday_change_pct = (spy_current - spy_open) / spy_open * 100

                # Bounce detection: current price recovered >= 0.3% above session low
                spy_low = spy_intra["Low"].min()
                spy_intraday_low = round(spy_low, 2)
                spy_bounce_pct = (spy_current - spy_low) / spy_low * 100 if spy_low > 0 else 0
                spy_bouncing = spy_bounce_pct >= 0.3 and spy_current > spy_open
        except Exception:
            pass

        # SPY S/R level detection and bounce rate
        spy_at_support = False
        spy_at_resistance = False
        spy_level_label = ""
        spy_support_bounce_rate = 0.5
        try:
            # Use intraday close when available, else daily close
            spy_price = spy_current if "spy_current" in dir() and spy_current > 0 else close

            # Prior day low/high (date-aware, same logic as fetch_prior_day)
            today = pd.Timestamp.now().normalize()
            last_bar_date = hist.index[-1].normalize()
            if last_bar_date >= today:
                if len(hist) >= 3:
                    spy_pd_high = hist["High"].iloc[-2]
                    spy_pd_low = hist["Low"].iloc[-2]
                else:
                    spy_pd_high = spy_pd_low = 0
            else:
                spy_pd_high = hist["High"].iloc[-1]
                spy_pd_low = hist["Low"].iloc[-1]

            # Prior week low/high (resample W-FRI, same pattern as fetch_prior_day)
            spy_pw_high = 0
            spy_pw_low = 0
            weekly = hist[["High", "Low"]].resample("W-FRI").agg({
                "High": "max", "Low": "min",
            }).dropna()
            if len(weekly) >= 2:
                last_weekly_date = weekly.index[-1].normalize()
                if last_bar_date <= last_weekly_date:
                    pw = weekly.iloc[-2]
                else:
                    pw = weekly.iloc[-1]
                spy_pw_high = pw["High"]
                spy_pw_low = pw["Low"]

            # Proximity checks — support first, then resistance
            if spy_pd_low > 0:
                pdl_prox = abs(spy_price - spy_pd_low) / spy_pd_low
                if pdl_prox <= SPY_SUPPORT_PROXIMITY_PCT:
                    spy_at_support = True
                    spy_level_label = f"prior day low ${spy_pd_low:.2f}"

            if not spy_at_support and spy_pw_low > 0:
                pwl_prox = abs(spy_price - spy_pw_low) / spy_pw_low
                if pwl_prox <= SPY_WEEKLY_PROXIMITY_PCT:
                    spy_at_support = True
                    spy_level_label = f"prior week low ${spy_pw_low:.2f}"

            if not spy_at_support and spy_pd_high > 0:
                pdh_prox = abs(spy_price - spy_pd_high) / spy_pd_high
                if pdh_prox <= SPY_SUPPORT_PROXIMITY_PCT:
                    spy_at_resistance = True
                    spy_level_label = f"prior day high ${spy_pd_high:.2f}"

            if not spy_at_support and not spy_at_resistance and spy_pw_high > 0:
                pwh_prox = abs(spy_price - spy_pw_high) / spy_pw_high
                if pwh_prox <= SPY_WEEKLY_PROXIMITY_PCT:
                    spy_at_resistance = True
                    spy_level_label = f"prior week high ${spy_pw_high:.2f}"

            # Bounce rate from historical data
            bounce_stats = _compute_spy_bounce_rate(hist)
            spy_support_bounce_rate = bounce_stats["bounce_rate"]
        except Exception:
            pass

        return {
            "trend": trend,
            "close": round(close, 2),
            "ma20": round(ma20, 2),
            "ma5": round(ma5, 2),
            "ma50": round(ma50, 2),
            "regime": regime,
            "intraday_change_pct": round(intraday_change_pct, 2),
            "spy_bouncing": spy_bouncing,
            "spy_intraday_low": spy_intraday_low,
            "spy_at_support": spy_at_support,
            "spy_at_resistance": spy_at_resistance,
            "spy_level_label": spy_level_label,
            "spy_support_bounce_rate": spy_support_bounce_rate,
            "spy_rsi14": spy_rsi14,
            "spy_ema20": round(spy_ema20, 2),
            "spy_ema50": round(spy_ema50, 2),
            "spy_ema_spread_pct": round(spy_ema_spread_pct, 2),
            "spy_at_ma_support": spy_at_ma_support,
            "spy_ema_regime": spy_ema_regime,
        }
    except Exception:
        return _default


def classify_market_regime(close: float, ma5: float, ma20: float, ma50: float) -> str:
    """Classify market regime based on price vs moving averages.

    Returns one of: TRENDING_UP, PULLBACK, TRENDING_DOWN, CHOPPY.
    """
    if close > ma5 and ma5 > ma20 and ma20 > ma50:
        return "TRENDING_UP"
    if close < ma5 and close > ma20:
        return "PULLBACK"
    if close < ma5 and close < ma20 and close < ma50:
        return "TRENDING_DOWN"
    return "CHOPPY"


def compute_vwap(bars: pd.DataFrame) -> pd.Series:
    """Compute VWAP from intraday OHLCV bars."""
    if bars.empty or "Volume" not in bars.columns:
        return pd.Series(dtype=float)
    typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
    cum_vol = bars["Volume"].cumsum()
    cum_tp_vol = (typical * bars["Volume"]).cumsum()
    return cum_tp_vol / cum_vol


def detect_intraday_supports(bars_5m: pd.DataFrame, min_bounce_pct: float = 0.002) -> list[dict]:
    """Find intraday support levels from hourly lows that held.

    Resamples 5-min bars to 1-hour, identifies hourly lows where
    the next hour's low stayed above and price bounced.

    Returns list of dicts with keys: level, touch_count, hold_hours, strength.
    """
    if bars_5m.empty or len(bars_5m) < 12:  # need at least 1 hour of data
        return []

    hourly = bars_5m.resample("1h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    # Step 1: find raw support levels (existing logic)
    raw_levels: list[float] = []
    for i in range(len(hourly) - 1):
        hour_low = hourly["Low"].iloc[i]
        next_low = hourly["Low"].iloc[i + 1]
        next_close = hourly["Close"].iloc[i + 1]
        bounce = (next_close - hour_low) / hour_low if hour_low > 0 else 0
        if next_low >= hour_low * 0.999 and bounce >= min_bounce_pct:
            raw_levels.append(round(hour_low, 2))

    if not raw_levels:
        return []

    # Step 2: cluster nearby levels within 0.3%, take average as representative
    raw_levels.sort()
    clusters: list[list[float]] = [[raw_levels[0]]]
    for level in raw_levels[1:]:
        if (level - clusters[-1][0]) / clusters[-1][0] <= 0.003:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    supports: list[dict] = []
    for cluster in clusters:
        rep_level = round(sum(cluster) / len(cluster), 2)

        # Step 3: count touches — hourly lows within 0.3% of representative level
        touch_count = 0
        for i in range(len(hourly)):
            if rep_level > 0 and abs(hourly["Low"].iloc[i] - rep_level) / rep_level <= 0.003:
                touch_count += 1

        # Step 4: count hold_hours — consecutive hours price stayed above level
        hold_hours = 0
        max_hold = 0
        for i in range(len(hourly)):
            if rep_level > 0 and hourly["Low"].iloc[i] >= rep_level * 0.999:
                hold_hours += 1
                max_hold = max(max_hold, hold_hours)
            else:
                hold_hours = 0

        # Step 5: assign strength
        strength = (
            "strong"
            if touch_count >= SUPPORT_STRONG_RETEST_COUNT
            and max_hold >= SUPPORT_STRONG_HOLD_HOURS
            else "weak"
        )

        supports.append({
            "level": rep_level,
            "touch_count": touch_count,
            "hold_hours": max_hold,
            "strength": strength,
        })

    return supports


def detect_5m_swing_lows(
    bars_5m: pd.DataFrame,
    min_bounce_pct: float = 0.002,
    cluster_pct: float = 0.003,
) -> list[dict]:
    """Find swing low supports from 5-min bars for fast detection.

    A swing low at bar *i*: Low[i] < Low[i-1] AND Low[i] < Low[i+1],
    with a minimum bounce (next bar close >= low * (1 + min_bounce_pct))
    to filter noise.

    Returns list of dicts matching detect_intraday_supports() format:
    level, touch_count, hold_hours (always 0), strength ("weak").
    """
    if bars_5m.empty or len(bars_5m) < 3:
        return []

    # Step 1: find swing lows with bounce confirmation
    raw_levels: list[float] = []
    for i in range(1, len(bars_5m) - 1):
        low_i = bars_5m["Low"].iloc[i]
        if low_i <= 0:
            continue
        if (low_i < bars_5m["Low"].iloc[i - 1]
                and low_i < bars_5m["Low"].iloc[i + 1]):
            # Require minimum bounce on next bar
            next_close = bars_5m["Close"].iloc[i + 1]
            bounce = (next_close - low_i) / low_i
            if bounce >= min_bounce_pct:
                raw_levels.append(round(float(low_i), 2))

    if not raw_levels:
        return []

    # Step 2: cluster nearby levels
    raw_levels.sort()
    clusters: list[list[float]] = [[raw_levels[0]]]
    for level in raw_levels[1:]:
        if (level - clusters[-1][0]) / clusters[-1][0] <= cluster_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    # Step 3: build support dicts (same format as detect_intraday_supports)
    supports: list[dict] = []
    for cluster in clusters:
        rep_level = round(min(cluster), 2)  # use lowest in cluster

        # Count touches: bar lows within 0.3% of representative level
        touch_count = 0
        for i in range(len(bars_5m)):
            if abs(bars_5m["Low"].iloc[i] - rep_level) / rep_level <= cluster_pct:
                touch_count += 1

        supports.append({
            "level": rep_level,
            "touch_count": touch_count,
            "hold_hours": 0,
            "strength": "weak",
        })

    return supports


def classify_gap(today_open: float, prior_close: float, prior_range: float) -> dict:
    """Classify gap type and size."""
    if prior_close <= 0:
        return {"type": "flat", "gap_pct": 0.0}
    gap_pct = (today_open - prior_close) / prior_close * 100
    if abs(gap_pct) < 0.3:
        return {"type": "flat", "gap_pct": round(gap_pct, 2)}
    if gap_pct > 0:
        return {"type": "gap_up", "gap_pct": round(gap_pct, 2)}
    return {"type": "gap_down", "gap_pct": round(gap_pct, 2)}


def compute_opening_range(bars_5m: pd.DataFrame) -> dict | None:
    """Compute the opening range from the first 30 minutes of 5-min bars.

    Takes first 6 bars (6 * 5min = 30 minutes: 9:30-10:00).
    Returns dict with or_high, or_low, or_range, or_range_pct, or_complete.
    Returns None if fewer than 6 bars.
    """
    if bars_5m.empty or len(bars_5m) < 6:
        return None

    or_bars = bars_5m.iloc[:6]
    or_high = or_bars["High"].max()
    or_low = or_bars["Low"].min()
    or_range = or_high - or_low
    or_range_pct = or_range / or_low if or_low > 0 else 0.0

    return {
        "or_high": or_high,
        "or_low": or_low,
        "or_range": or_range,
        "or_range_pct": or_range_pct,
        "or_complete": len(bars_5m) >= 6,
    }


def check_mtf_alignment(bars_5m: pd.DataFrame) -> dict:
    """Check multi-timeframe alignment by resampling 5-min to 15-min.

    Computes EMA5 and EMA20 on 15-min closes. A single day gives ~26
    fifteen-minute bars — enough for EMA20.

    Returns dict with mtf_aligned, ema5_15m, ema20_15m, mtf_trend.
    """
    result = {"mtf_aligned": False, "ema5_15m": 0.0, "ema20_15m": 0.0, "mtf_trend": "neutral"}

    if bars_5m.empty or len(bars_5m) < 15:  # need at least 5 fifteen-min bars
        return result

    bars_15m = bars_5m.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()

    if len(bars_15m) < 5:
        return result

    ema5 = bars_15m["Close"].ewm(span=5, adjust=False).mean()
    ema20 = bars_15m["Close"].ewm(span=20, adjust=False).mean()

    ema5_val = ema5.iloc[-1]
    ema20_val = ema20.iloc[-1]
    aligned = ema5_val > ema20_val

    return {
        "mtf_aligned": bool(aligned),
        "ema5_15m": round(ema5_val, 2),
        "ema20_15m": round(ema20_val, 2),
        "mtf_trend": "bullish" if aligned else "bearish",
    }


def track_gap_fill(bars_5m: pd.DataFrame, today_open: float, prior_close: float) -> dict:
    """Track gap fill progress throughout the day.

    Returns dict with gap_size, gap_pct, gap_direction, fill_pct, is_filled.
    """
    result = {
        "gap_size": 0.0, "gap_pct": 0.0, "gap_direction": "flat",
        "fill_pct": 0.0, "is_filled": False,
    }

    if prior_close <= 0 or bars_5m.empty:
        return result

    gap_size = today_open - prior_close
    gap_pct = gap_size / prior_close * 100

    if abs(gap_pct) < 0.3:
        result["gap_direction"] = "flat"
        return result

    result["gap_size"] = gap_size
    result["gap_pct"] = round(gap_pct, 2)

    if gap_size > 0:
        # Gap up: fills when any bar low <= prior_close
        result["gap_direction"] = "gap_up"
        min_low = bars_5m["Low"].min()
        if min_low <= prior_close:
            result["is_filled"] = True
            result["fill_pct"] = 100.0
        else:
            filled = today_open - min_low
            result["fill_pct"] = round(filled / gap_size * 100, 1) if gap_size > 0 else 0.0
    else:
        # Gap down: fills when any bar high >= prior_close
        result["gap_direction"] = "gap_down"
        max_high = bars_5m["High"].max()
        if max_high >= prior_close:
            result["is_filled"] = True
            result["fill_pct"] = 100.0
        else:
            filled = max_high - today_open
            result["fill_pct"] = round(filled / abs(gap_size) * 100, 1) if gap_size != 0 else 0.0

    return result


def fetch_historical_intraday(
    symbol: str, target_date: str, interval: str = "5m",
) -> pd.DataFrame:
    """Fetch historical intraday bars for a specific date.

    Uses yfinance with explicit start/end dates. yfinance keeps ~59 days
    of intraday data.

    Args:
        symbol: Ticker symbol.
        target_date: ISO date string (e.g., "2025-05-01").
        interval: Bar interval (default "5m").

    Returns DataFrame with OHLCV columns, or empty DataFrame on failure.
    """
    try:
        start = pd.Timestamp(target_date)
        end = start + pd.Timedelta(days=1)
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval=interval)
        if hist.empty:
            return pd.DataFrame()
        hist = _normalize_index_to_et(hist)
        return hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()
