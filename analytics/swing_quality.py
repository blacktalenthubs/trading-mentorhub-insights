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
    ("EMA 21", "ema", 21),
    ("EMA 50", "ema", 50),
    ("SMA 50", "sma", 50),
    ("EMA 100", "ema", 100),
    ("SMA 100", "sma", 100),
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
    """Qualify one symbol on its latest daily bar for the given market regime.
    Returns a SwingQualification when a rule is met, else None. Deterministic."""
    cfg = config or DEFAULT_CONFIG
    df = _normalize(daily)
    if df is None:
        return None
    if regime == REGIME_RSI:
        return _evaluate_rsi(symbol, df, cfg, session_date)
    return _evaluate_bounce(symbol, df, cfg, session_date)


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
