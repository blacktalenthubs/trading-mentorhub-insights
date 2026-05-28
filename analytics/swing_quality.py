"""Deterministic swing-trade qualification for the AI scan (spec 56).

Two regimes, switched by where SPY sits relative to its 21 EMA:

  * BOUNCE (SPY at/above its 21 EMA) — a stock trending above its key MAs
    (bullish stack: 50 > 100 > 200) pulls back so the day's low tags a key MA
    and the candle closes back above it. Entry = that MA, stop = the day's low.
  * RSI (SPY below its 21 EMA) — a stock's RSI(14) closes back above 30 after
    being oversold. Entry = the close, stop = the day's low.

A swing exits on the first daily CLOSE below its stop (the entry-day low).

Key MAs: 21 EMA, and the 50 / 100 / 200 in both EMA and SMA (seven in all).

Pure and deterministic — no I/O, no network, no LLM. Same inputs -> same output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Key MAs a bounce can defend: (label, kind, period).
_KEY_MAS: list[tuple[str, str, int]] = [
    # User-trimmed 2026-05-28 — focus on high-conviction levels only.
    # EMA 100 / SMA 100 dropped (too noisy, redundant with 50 and 200).
    ("EMA 21", "ema", 21),
    ("EMA 50", "ema", 50),
    ("SMA 50", "sma", 50),
    ("EMA 200", "ema", 200),
    ("SMA 200", "sma", 200),
]

_MIN_BARS_RSI = 30        # RSI(14) needs a short history to settle
_MIN_BARS_BOUNCE = 210    # enough to seat the 200 EMA plus a prior bar
_T1_PCT = 0.05            # swing target 1 — 5%
_T2_PCT = 0.10            # swing target 2 — 10%

REGIME_BOUNCE = "bounce"
REGIME_RSI = "rsi"


@dataclass
class SwingQualityConfig:
    """Tuning knobs for the qualification rules."""
    oversold_lookback: int = 7      # bars to look back for an RSI <= 30 reading
    rsi_period: int = 14
    rsi_oversold: float = 30.0


DEFAULT_CONFIG = SwingQualityConfig()


@dataclass
class SwingRuleHit:
    """One qualifying rule the latest bar met."""
    rule: str    # "ma_hold" | "ma_reclaim" | "rsi_recovery"
    level: str   # "EMA 50" / "SMA 200" / "RSI 30"
    detail: str  # human-readable specifics


@dataclass
class SwingQualification:
    """The result of qualifying one symbol on its latest daily bar."""
    symbol: str
    direction: str                       # always "LONG"
    mode: str                            # "bounce" | "rsi"
    entry_level: str = ""                # MA defended ("EMA 50") or "RSI 30"
    rules: list[SwingRuleHit] = field(default_factory=list)
    entry: float = 0.0
    stop: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    close: float = 0.0
    session_date: str = ""
    summary: str = ""


# ── Indicators (computed from the daily close series) ────────────────


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _ma_series(close: pd.Series, kind: str, period: int) -> pd.Series:
    return _ema(close, period) if kind == "ema" else _sma(close, period)


def _normalize(daily) -> pd.DataFrame | None:
    """Accept a DataFrame (any column case) or a list of OHLC dicts; return a
    DataFrame with lowercase open/high/low/close columns, oldest-first."""
    if daily is None:
        return None
    df = daily if isinstance(daily, pd.DataFrame) else pd.DataFrame(list(daily))
    if df.empty:
        return None
    df = df.rename(columns={c: str(c).lower() for c in df.columns})
    if not {"open", "high", "low", "close"}.issubset(df.columns):
        return None
    return df.reset_index(drop=True)


# ── Market regime (SPY) ──────────────────────────────────────────────


def spy_regime(spy_daily) -> str:
    """BOUNCE when SPY's latest daily close is at/above its 21 EMA, else RSI.

    This is the only market gate: SPY above the 21 EMA -> hunt key-MA bounces;
    SPY below it -> the market is weak, hunt oversold RSI recoveries instead.
    Defaults to BOUNCE when SPY history is unavailable (the normal regime)."""
    df = _normalize(spy_daily)
    if df is None or len(df) < 21:
        return REGIME_BOUNCE
    close = df["close"].astype(float)
    ema21 = float(_ema(close, 21).iloc[-1])
    return REGIME_BOUNCE if float(close.iloc[-1]) >= ema21 else REGIME_RSI


# ── Exit rule ────────────────────────────────────────────────────────


def swing_exit_triggered(stop: float, latest_close: float) -> bool:
    """A swing exits on the first daily CLOSE below its stop (the entry-day
    low). An intraday wick under the stop that closes back above does NOT
    exit — only a close below it, even slightly, breaks the thesis."""
    return float(latest_close) < float(stop)


# ── Public entrypoint ────────────────────────────────────────────────


def evaluate_swing_quality(
    symbol: str,
    daily,
    regime: str,
    config: SwingQualityConfig | None = None,
    session_date: str = "",
) -> SwingQualification | None:
    """Qualify one symbol on its latest daily bar.

    2026-05-28 — regime-gating removed. All three rule categories run on
    every symbol; the SPY-regime label is now context-only (shown in the
    UI badge) and no longer suppresses RSI or crossover rules when SPY
    is healthy. The full live rule set (per user spec):
      - Key-MA bounce (EMA21, EMA50, SMA50, EMA200, SMA200), gated by bullish stack
      - EMA 8/21 bullish crossover, gated by price above EMA 50
      - RSI(14) close back above 30 from oversold — always allowed
    First rule to qualify produces the SwingQualification. Bounce first,
    then crossover, then RSI — order = strongest evidence first.
    """
    _ = regime  # kept for backward-compat with callers
    cfg = config or DEFAULT_CONFIG
    df = _normalize(daily)
    if df is None:
        return None
    return (
        _evaluate_bounce(symbol, df, cfg, session_date)
        or _evaluate_crossover(symbol, df, cfg, session_date)
        or _evaluate_golden_cross_retest(symbol, df, cfg, session_date)
        or _evaluate_52w_high_retest(symbol, df, cfg, session_date)
        or _evaluate_5day_low_reclaim(symbol, df, cfg, session_date)
        or _evaluate_rsi(symbol, df, cfg, session_date)
    )


def _evaluate_crossover(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """EMA 8/21 bullish crossover — the 8 EMA closes above the 21 EMA on
    the most recent bar after being below it the bar before. Momentum
    trigger (not a bounce). Gated by price above EMA 50 so we're not
    chasing a counter-trend bounce in a clean downtrend."""
    _ = cfg
    if len(df) < 60:
        return None
    close = df["close"].astype(float)
    ema8 = _ema(close, 8)
    ema21 = _ema(close, 21)
    ema50 = _ema(close, 50)
    if pd.isna(ema8.iloc[-1]) or pd.isna(ema21.iloc[-1]) or pd.isna(ema50.iloc[-1]):
        return None
    e8_now, e21_now = float(ema8.iloc[-1]), float(ema21.iloc[-1])
    e8_prev, e21_prev = float(ema8.iloc[-2]), float(ema21.iloc[-2])
    if not (e8_prev <= e21_prev and e8_now > e21_now):
        return None
    latest_close = float(close.iloc[-1])
    if latest_close < float(ema50.iloc[-1]):
        return None  # crossover under the 50 EMA — counter-trend, skip
    latest_low = float(df["low"].astype(float).iloc[-1])
    hits = [SwingRuleHit(
        "ema_8_21_cross", "EMA 8/21 cross",
        f"EMA 8 (${e8_now:.2f}) crossed above EMA 21 (${e21_now:.2f}) "
        f"— momentum flip with price above EMA 50",
    )]
    return _build(symbol, REGIME_BOUNCE, hits, "EMA 21", e21_now,
                  latest_low, latest_close, session_date)


def _evaluate_golden_cross_retest(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """Daily 50 EMA above 200 EMA (golden-cross state) AND today's low
    tagged the 50 EMA AND closed above it. The retest of the golden-cross
    level — much higher quality than the bare cross because we wait for
    the pullback. Cross must have happened within last 30 bars (recent).
    """
    _ = cfg
    if len(df) < 230:
        return None
    close = df["close"].astype(float)
    low = df["low"].astype(float)
    ema50 = _ema(close, 50)
    ema200 = _ema(close, 200)
    if pd.isna(ema50.iloc[-1]) or pd.isna(ema200.iloc[-1]):
        return None
    if float(ema50.iloc[-1]) <= float(ema200.iloc[-1]):
        return None  # not in golden-cross state
    recent = 30
    crossed_recently = False
    for i in range(max(1, len(ema50) - recent), len(ema50)):
        if pd.isna(ema50.iloc[i - 1]) or pd.isna(ema200.iloc[i - 1]):
            continue
        if float(ema50.iloc[i - 1]) <= float(ema200.iloc[i - 1]) \
                and float(ema50.iloc[i]) > float(ema200.iloc[i]):
            crossed_recently = True
            break
    if not crossed_recently:
        return None
    ma_now = float(ema50.iloc[-1])
    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    if not (latest_low <= ma_now < latest_close):
        return None
    hits = [SwingRuleHit(
        "golden_cross_retest", "EMA 50 (golden cross)",
        f"50 EMA crossed above 200 EMA in the last {recent} bars and today's "
        f"low retested the 50 EMA (${ma_now:.2f}) before closing above",
    )]
    return _build(symbol, REGIME_BOUNCE, hits, "EMA 50", ma_now,
                  latest_low, latest_close, session_date)


def _evaluate_52w_high_retest(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """Broke to a new 52-week high within the last ~10 bars, then today's
    pullback retested that prior 52w-high level (now support) and closed
    above. Classic continuation entry on names that grind higher."""
    _ = cfg
    if len(df) < 260:
        return None
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    # Prior 52w-high level = the rolling 252-bar high as of N bars ago.
    lookback = 12
    if len(close) < 252 + lookback:
        return None
    prior_52w_high = float(high.iloc[-(252 + lookback):-lookback].max())
    # Has the latest cluster of bars (excluding today) broken above it?
    recent_window = close.iloc[-lookback:-1]
    if len(recent_window) == 0 or float(recent_window.max()) <= prior_52w_high:
        return None
    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    # Today's low retested the prior 52w-high level (now support), close > it
    tol = prior_52w_high * 0.003  # 0.3% tolerance for "tagged"
    if not (latest_low <= prior_52w_high + tol and latest_close > prior_52w_high):
        return None
    hits = [SwingRuleHit(
        "52w_high_retest", "52w-high retest",
        f"broke a new 52-week high recently; today's low retested the prior "
        f"high (${prior_52w_high:.2f}) and closed above — continuation entry",
    )]
    return _build(symbol, REGIME_BOUNCE, hits, "52w high", prior_52w_high,
                  latest_low, latest_close, session_date)


def _evaluate_5day_low_reclaim(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """Stock printed a 5-day low and closed back above it the same day
    (intraday recovery) with above-average volume. Price-based mean
    reversion — cleaner than RSI because it's a structural level, not
    an oscillator reading. Requires daily volume > 1.2× 20-day avg."""
    _ = cfg
    if len(df) < 30:
        return None
    close = df["close"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float) if "volume" in df.columns else None
    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    prior_5day_low = float(low.iloc[-6:-1].min())  # 5 bars before today
    # Today wicked below the 5-day low but closed above it
    if not (latest_low < prior_5day_low and latest_close > prior_5day_low):
        return None
    # Volume confirmation
    if volume is not None and not pd.isna(volume.iloc[-1]):
        vol_avg = float(volume.iloc[-21:-1].mean()) if len(volume) >= 21 else None
        if vol_avg and float(volume.iloc[-1]) < 1.2 * vol_avg:
            return None
    hits = [SwingRuleHit(
        "5day_low_reclaim", "5-day-low reclaim",
        f"wicked below the 5-day low (${prior_5day_low:.2f}) and closed back "
        f"above with above-average volume — mean-reversion entry",
    )]
    return _build(symbol, REGIME_BOUNCE, hits, "5-day low", prior_5day_low,
                  latest_low, latest_close, session_date)


def _evaluate_bounce(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """BOUNCE regime — key-MA defense / reclaim inside a bullish MA stack."""
    if len(df) < _MIN_BARS_BOUNCE:
        return None

    close = df["close"].astype(float)
    low = df["low"].astype(float)
    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])
    prev_close = float(close.iloc[-2])

    # Stack filter — the symbol must trend ABOVE its key MAs, with the MAs in
    # bullish ascending order. A stock with its MAs stacked above price is in a
    # downtrend and is not a swing candidate, no matter what one bar does.
    ema50 = float(_ema(close, 50).iloc[-1])
    ema100 = float(_ema(close, 100).iloc[-1])
    ema200 = float(_ema(close, 200).iloc[-1])
    if not (ema50 > ema100 > ema200 and latest_close > ema200):
        return None

    hits: list[SwingRuleHit] = []
    levels: list[tuple[str, float]] = []
    for label, kind, period in _KEY_MAS:
        ma = _ma_series(close, kind, period)
        ma_now = ma.iloc[-1]
        ma_prev = ma.iloc[-2]
        if pd.isna(ma_now) or pd.isna(ma_prev):
            continue  # not enough history for this MA
        ma_now = float(ma_now)
        # The day's low must REACH the MA and the candle must CLOSE above it.
        if latest_low <= ma_now < latest_close:
            was_above = prev_close >= float(ma_prev)
            rule = "ma_hold" if was_above else "ma_reclaim"
            verb = "held" if was_above else "reclaimed"
            hits.append(SwingRuleHit(
                rule, label,
                f"{verb} the {label} (${ma_now:.2f}) — the day's low tagged it "
                f"and the candle closed back above",
            ))
            levels.append((label, ma_now))

    if not hits:
        return None

    # Entry = the highest defended MA (the nearest support below price), so the
    # entry sits at the level, not at an extended close. Stop = the day's low.
    entry_label, entry = max(levels, key=lambda lv: lv[1])
    return _build(symbol, REGIME_BOUNCE, hits, entry_label, entry,
                  latest_low, latest_close, session_date)


def _evaluate_rsi(
    symbol: str, df: pd.DataFrame, cfg: SwingQualityConfig, session_date: str
) -> SwingQualification | None:
    """RSI regime — oversold-RSI recovery. Used only when SPY is below its
    21 EMA: in a market-wide sell-off nothing holds its MAs, so the qualifier
    is RSI(14) closing back above 30 after being oversold."""
    if len(df) < _MIN_BARS_RSI:
        return None

    close = df["close"].astype(float)
    low = df["low"].astype(float)
    latest_close = float(close.iloc[-1])
    latest_low = float(low.iloc[-1])

    rsi = _rsi(close, cfg.rsi_period)
    rsi_now = rsi.iloc[-1]
    if pd.isna(rsi_now) or float(rsi_now) <= cfg.rsi_oversold:
        return None
    window = rsi.iloc[-(cfg.oversold_lookback + 1):-1]
    if len(window) == 0:
        return None
    prior_min = window.min()
    if pd.isna(prior_min) or float(prior_min) > cfg.rsi_oversold:
        return None

    hits = [SwingRuleHit(
        "rsi_recovery", "RSI 30",
        f"RSI(14) closed at {float(rsi_now):.0f}, up from {float(prior_min):.0f} "
        f"(oversold) — recovering after a market sell-off",
    )]
    return _build(symbol, REGIME_RSI, hits, "RSI 30", latest_close, latest_low,
                  latest_close, session_date)


def _build(
    symbol: str, mode: str, hits: list[SwingRuleHit], entry_level: str,
    entry: float, stop: float, latest_close: float, session_date: str,
) -> SwingQualification:
    return SwingQualification(
        symbol=symbol,
        direction="LONG",
        mode=mode,
        entry_level=entry_level,
        rules=hits,
        entry=round(entry, 2),
        stop=round(stop, 2),
        target_1=round(entry * (1.0 + _T1_PCT), 2),
        target_2=round(entry * (1.0 + _T2_PCT), 2),
        close=round(latest_close, 2),
        session_date=session_date,
        summary=_compose_summary(hits, mode),
    )


def _compose_summary(hits: list[SwingRuleHit], mode: str) -> str:
    """Plain-language 'why it qualified' from the rule hits (FR-007)."""
    phrases: list[str] = []
    for h in hits:
        if h.rule == "ma_hold":
            phrases.append(f"held the {h.level} after a pullback")
        elif h.rule == "ma_reclaim":
            phrases.append(f"reclaimed the {h.level}")
        elif h.rule == "rsi_recovery":
            phrases.append("RSI recovered back above 30 after being oversold")
    return "Swing setup: " + "; ".join(phrases) + "."
