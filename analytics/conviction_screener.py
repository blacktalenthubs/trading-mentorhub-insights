"""Conviction screener — long-term, analyst-backed uptrend finder.

Goal: surface mid-cap AI / chips / disruptive-tech names that combine
(1) a *strong analyst rating*, (2) a *persistent uptrend above the 50-day MA*,
and (3) *relative strength vs SPY* — the profile of names like ZETA/NBIS that
trend for months. This is a curation + scoring layer; it does not touch any
alert/business-logic file (Constitution §1).

Pure functions here take already-fetched daily bars + an analyst dict, so they
are deterministic and unit-testable. The DB orchestration (fetch + persist)
lives in api/app/services/screener_service.py, mirroring the swing screener.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd


# --- Curated universe: AI / chips / disruptive mid-caps, tagged by theme ---
# Kept deliberately mid/small-cap-leaning; mega names that grow past the cap are
# trimmed at scan time by MARKET_CAP_CEILING. (symbol, theme)
CONVICTION_UNIVERSE: tuple[tuple[str, str], ...] = (
    # AI / connectivity / specialty chips
    ("CRDO", "AI Chips"), ("ALAB", "AI Chips"), ("LSCC", "AI Chips"),
    ("AMBA", "AI Chips"), ("SITM", "AI Chips"), ("MTSI", "AI Chips"),
    ("RMBS", "AI Chips"), ("POWI", "AI Chips"), ("INDI", "AI Chips"),
    ("AEHR", "AI Chips"), ("ACLS", "AI Chips"), ("SLAB", "AI Chips"),
    ("DIOD", "AI Chips"), ("AOSL", "AI Chips"),
    # Semicap — "picks & shovels"
    ("NVMI", "Semicap"), ("CAMT", "Semicap"), ("ONTO", "Semicap"),
    ("UCTT", "Semicap"), ("ACMR", "Semicap"), ("KLIC", "Semicap"),
    ("FORM", "Semicap"),
    # AI software / data / infra
    ("NBIS", "AI Infra"), ("CRWV", "AI Infra"), ("TEM", "AI Software"),
    ("BBAI", "AI Software"), ("SOUN", "AI Software"), ("GTLB", "AI Software"),
    ("S", "AI Software"), ("PATH", "AI Software"), ("CFLT", "AI Software"),
    ("ESTC", "AI Software"), ("PD", "AI Software"), ("FROG", "AI Software"),
    ("RXRX", "AI Software"), ("AI", "AI Software"), ("ZETA", "AI Software"),
    # AI optics / networking
    ("AAOI", "AI Optics"), ("LITE", "AI Optics"), ("FN", "AI Optics"),
    # Disruptive — quantum / power / space / robotics
    ("IONQ", "Disruptive"), ("RGTI", "Disruptive"), ("QBTS", "Disruptive"),
    ("OKLO", "Disruptive"), ("SMR", "Disruptive"), ("BE", "Disruptive"),
    ("ASTS", "Disruptive"), ("RKLB", "Disruptive"), ("ACHR", "Disruptive"),
    ("OUST", "Disruptive"),
)

# A name above this market cap is no longer "mid-cap" — drop it (we want the next
# NBIS, not the current mega-caps). None marketCap (data miss) is kept.
MARKET_CAP_CEILING = 50_000_000_000.0

# Exclude names whose analyst consensus is clearly NOT a buy. recommendationMean
# is 1=Strong Buy … 5=Sell; >2.7 ≈ Hold-or-worse. Names with no/low coverage are
# kept (can't disprove) but score lower. A covered name needs ≥ this many analysts
# for the rating to gate.
REC_MEAN_MAX = 2.7
MIN_ANALYSTS_TO_GATE = 4

LOOKBACK_PERSIST = 60   # window for "% of days held above the 50MA"
MIN_BARS = 110          # need ≥50 (MA) + ~60 (persistence) bars to score well


@dataclass
class ConvictionCandidate:
    symbol: str
    theme: str
    last_price: float
    market_cap: Optional[float]
    sector: Optional[str]
    # trend
    above_ma50: bool
    above_ma200: bool
    ma_stacked: bool
    pct_days_above_50: float     # 0–100, over the last LOOKBACK_PERSIST sessions
    ma50_slope_up: bool
    ret_20d: float
    rs_vs_spy: float
    # analyst conviction
    rec_mean: Optional[float]
    rec_key: Optional[str]
    num_analysts: Optional[int]
    target_mean: Optional[float]
    target_upside_pct: Optional[float]
    # composite
    score: int
    grade: str
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _last(series: pd.Series) -> Optional[float]:
    try:
        v = float(series.iloc[-1])
        return v if v == v else None  # drop NaN
    except Exception:
        return None


def _grade(score: int) -> str:
    return "A" if score >= 70 else "B" if score >= 50 else "C"


def evaluate_conviction(
    symbol: str,
    theme: str,
    daily: Optional[pd.DataFrame],
    spy_ret_20d: float,
    analyst: dict,
) -> Optional[ConvictionCandidate]:
    """Score one symbol. Returns None if it fails the hard gates (not enough
    history, not above the 50MA, or a clearly weak analyst rating, or too big)."""
    if daily is None or daily.empty or "Close" not in daily or len(daily) < 60:
        return None
    closes = daily["Close"].astype(float)
    n = len(closes)

    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean() if n >= 200 else None

    last_close = _last(closes)
    s50 = _last(sma50)
    if last_close is None or s50 is None:
        return None

    above_ma50 = last_close > s50
    if not above_ma50:
        return None  # hard gate — the whole point is "trends above the 50MA"

    s200 = _last(sma200) if sma200 is not None else None
    above_ma200 = bool(s200 is not None and last_close > s200)
    ma_stacked = bool(above_ma200 and s200 is not None and s50 > s200)

    # % of the last LOOKBACK_PERSIST sessions the close held above its 50MA
    win = min(LOOKBACK_PERSIST, n - 50) if n > 50 else 0
    if win > 0:
        c = closes.iloc[-win:]
        m = sma50.iloc[-win:]
        held = int((c.values >= m.values).sum())
        pct_days_above_50 = round(held / win * 100, 1)
    else:
        pct_days_above_50 = 0.0

    ma50_slope_up = bool(n >= 71 and float(sma50.iloc[-1]) > float(sma50.iloc[-21]))

    ret_20d = round((last_close / float(closes.iloc[-21]) - 1) * 100, 1) if n > 21 else 0.0
    rs_vs_spy = round(ret_20d - spy_ret_20d, 1)

    # --- analyst ---
    rec_mean = analyst.get("rec_mean")
    num_analysts = analyst.get("num_analysts")
    target_mean = analyst.get("target_mean")
    market_cap = analyst.get("market_cap")
    sector = analyst.get("sector")

    if market_cap and market_cap > MARKET_CAP_CEILING:
        return None  # not mid-cap anymore

    # Gate out names that ARE covered but rated Hold-or-worse.
    if (
        rec_mean is not None and num_analysts is not None
        and num_analysts >= MIN_ANALYSTS_TO_GATE and rec_mean > REC_MEAN_MAX
    ):
        return None

    target_upside_pct = (
        round((target_mean / last_close - 1) * 100, 1)
        if target_mean and last_close else None
    )

    # --- composite score (0–100) ---
    analyst_pts = (max(0.0, min(1.0, (3.0 - rec_mean) / 2.0)) * 35) if rec_mean else 0.0
    upside_pts = (max(0.0, min(target_upside_pct or 0.0, 50.0)) / 50.0) * 15
    persist_pts = (pct_days_above_50 / 100.0) * 20
    struct_pts = (10 if ma_stacked else 0) + (5 if ma50_slope_up else 0)
    rs_pts = (max(0.0, min(rs_vs_spy, 20.0)) / 20.0) * 15
    score = int(round(analyst_pts + upside_pts + persist_pts + struct_pts + rs_pts))

    return ConvictionCandidate(
        symbol=symbol, theme=theme, last_price=round(last_close, 2),
        market_cap=market_cap, sector=sector,
        above_ma50=above_ma50, above_ma200=above_ma200, ma_stacked=ma_stacked,
        pct_days_above_50=pct_days_above_50, ma50_slope_up=ma50_slope_up,
        ret_20d=ret_20d, rs_vs_spy=rs_vs_spy,
        rec_mean=round(rec_mean, 2) if rec_mean else None,
        rec_key=analyst.get("rec_key"), num_analysts=num_analysts,
        target_mean=round(target_mean, 2) if target_mean else None,
        target_upside_pct=target_upside_pct,
        score=score, grade=_grade(score),
    )


def fetch_analyst(symbol: str) -> dict:
    """Analyst consensus + cap/sector via yfinance .info. Best-effort — .info is
    heavier/rate-limited, so we run it only on the (infrequent) conviction scan and
    swallow failures (the symbol still scores on price action, just without ratings)."""
    try:
        import yfinance as yf  # lazy
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return {}
    return {
        "rec_mean": info.get("recommendationMean"),
        "rec_key": info.get("recommendationKey"),
        "num_analysts": info.get("numberOfAnalystOpinions"),
        "target_mean": info.get("targetMeanPrice"),
        "market_cap": info.get("marketCap"),
        "sector": info.get("sector"),
    }


def rank_conviction(cands: list[ConvictionCandidate], top_n: int = 40) -> list[ConvictionCandidate]:
    """Highest conviction first; assign 1-based rank."""
    ordered = sorted(cands, key=lambda c: c.score, reverse=True)[:top_n]
    for i, c in enumerate(ordered, start=1):
        c.rank = i
    return ordered
