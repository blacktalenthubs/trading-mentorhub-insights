"""Growth Leaders screener — the Mathematical Growth-Stock Framework (#64-M).

Ranks the universe by how well a name fits the profile of the all-time great growth
winners: a fundamental growth engine (revenue growth, earnings momentum, margins) +
relative-strength leadership in a Stage-2 uptrend. The "Long Term" board under Trade
Ideas; the conviction-screener sibling.

Pure + deterministic, exactly like conviction_screener.py: this module takes
already-fetched DAILY bars + a fundamentals dict (sourced from the symbol_fundamentals
table — NOT yfinance, so it's Railway-safe) and returns a scored candidate with a
transparent ✓/✗ scorecard. DB orchestration (fetch + persist) lives in
api/app/services/screener_service.py.

Score = 0–100 across the criteria we can measure today; the rest (ROIC, moat, runway)
are surfaced as "pending", never faked (grade-and-show).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

MIN_BARS_G = 160        # need ~150 (30wMA proxy) + headroom to score the trend
RS_WINDOW = 63          # ~3 months of sessions for the relative-strength read
HI_WINDOW = 252         # 52-week high lookback
ACCUM_WINDOW = 50       # up- vs down-day volume window (accumulation proxy)

# Criterion weights (max points). ROIC / moat / runway are not yet measurable → 0.
W_REV = 20.0            # revenue growth > 30% (full when also accelerating)
W_EARN = 15.0           # earnings momentum (EPS growth)
W_MARGIN = 10.0         # high gross margin
W_STAGE2 = 15.0         # Stage 2 (above a rising 30w-proxy MA)
W_RS = 20.0             # relative-strength leadership vs SPY (the #1 edge)
W_52WH = 10.0           # near the 52-week high
W_INST = 10.0           # institutional demand (accumulation / Buy consensus)


@dataclass
class GrowthCandidate:
    symbol: str
    sector: Optional[str]
    last_price: float
    # technical
    stage2: bool
    rs_vs_spy: float
    pct_off_52wh: Optional[float]
    accumulation: Optional[float]      # up/down-day volume ratio (>1 = accumulated)
    # fundamental
    rev_growth_pct: Optional[float]
    rev_accelerating: Optional[bool]
    eps_growth_pct: Optional[float]
    gross_margin_pct: Optional[float]
    consensus: Optional[str]           # Buy / Hold / Sell
    # per-criterion status: "pass" | "fail" | "pending"
    scorecard: dict
    score: int
    grade: str
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _lastf(series: pd.Series) -> Optional[float]:
    try:
        v = float(series.iloc[-1])
        return v if v == v else None
    except Exception:
        return None


def _grade(score: int) -> str:
    return "A" if score >= 70 else "B" if score >= 50 else "C"


def evaluate_growth(
    symbol: str,
    sector: Optional[str],
    daily: Optional[pd.DataFrame],
    spy_ret_window: float,
    fund: Optional[dict] = None,
) -> Optional[GrowthCandidate]:
    """Score one symbol. Returns None only on insufficient data — a name that fails
    a criterion still appears (graded down), never silently dropped.

    `fund` keys (all optional, from symbol_fundamentals): rev_growth_pct,
    rev_accelerating (bool), eps_growth_pct, gross_margin_pct, consensus, sector.
    `spy_ret_window` = SPY's % return over RS_WINDOW sessions (for the RS read).
    """
    if daily is None or daily.empty or "Close" not in daily or len(daily) < MIN_BARS_G:
        return None
    fund = fund or {}
    closes = daily["Close"].astype(float)
    vols = daily["Volume"].astype(float) if "Volume" in daily else None
    n = len(closes)
    last = _lastf(closes)
    if last is None or last <= 0:
        return None

    # ── technical ────────────────────────────────────────────────────────────
    sma50 = closes.rolling(50).mean()       # ~10-week
    sma150 = closes.rolling(150).mean()     # ~30-week (Weinstein)
    s50 = _lastf(sma50)
    s150 = _lastf(sma150)
    ma150_rising = n >= 171 and float(sma150.iloc[-1]) > float(sma150.iloc[-21])
    stage2 = bool(s150 is not None and last > s150 and ma150_rising and s50 is not None and s50 > s150)

    ret_window = (last / float(closes.iloc[-(RS_WINDOW + 1)]) - 1) * 100 if n > RS_WINDOW else 0.0
    rs_vs_spy = round(ret_window - spy_ret_window, 1)

    hi = float(closes.iloc[-HI_WINDOW:].max()) if n >= HI_WINDOW else float(closes.max())
    pct_off_52wh = round((hi - last) / hi * 100, 1) if hi else None

    accumulation: Optional[float] = None
    if vols is not None and n >= ACCUM_WINDOW + 1:
        chg = closes.diff().iloc[-ACCUM_WINDOW:]
        v = vols.iloc[-ACCUM_WINDOW:]
        up = float(v[chg > 0].sum())
        dn = float(v[chg < 0].sum())
        accumulation = round(up / dn, 2) if dn > 0 else None

    # ── fundamental (from symbol_fundamentals) ───────────────────────────────
    rev = fund.get("rev_growth_pct")
    rev_acc = fund.get("rev_accelerating")
    eps = fund.get("eps_growth_pct")
    gm = fund.get("gross_margin_pct")
    consensus = fund.get("consensus")

    sc: dict = {}
    pts = 0.0

    # revenue growth > 30% (full credit when ALSO accelerating)
    if rev is None:
        sc["rev_growth"] = "pending"
    elif rev >= 30.0:
        sc["rev_growth"] = "pass"
        pts += W_REV if rev_acc else W_REV * 0.75
    else:
        sc["rev_growth"] = "fail"

    # earnings momentum
    if eps is None:
        sc["earnings"] = "pending"
    elif eps >= 25.0:
        sc["earnings"] = "pass"
        pts += W_EARN
    elif eps > 0.0:
        sc["earnings"] = "pass"
        pts += W_EARN * 0.5
    else:
        sc["earnings"] = "fail"

    # high gross margin
    if gm is None:
        sc["gross_margin"] = "pending"
    elif gm >= 50.0:
        sc["gross_margin"] = "pass"
        pts += W_MARGIN
    elif gm >= 35.0:
        sc["gross_margin"] = "pass"
        pts += W_MARGIN * 0.5
    else:
        sc["gross_margin"] = "fail"

    # Stage 2
    sc["stage2"] = "pass" if stage2 else "fail"
    if stage2:
        pts += W_STAGE2

    # relative-strength leadership
    if rs_vs_spy > 0:
        sc["rs_leadership"] = "pass"
        pts += min(rs_vs_spy, 20.0) / 20.0 * W_RS
    else:
        sc["rs_leadership"] = "fail"

    # near the 52-week high
    if pct_off_52wh is None:
        sc["near_52wh"] = "pending"
    elif pct_off_52wh <= 10.0:
        sc["near_52wh"] = "pass"
        pts += W_52WH
    elif pct_off_52wh <= 20.0:
        sc["near_52wh"] = "pass"
        pts += W_52WH * 0.5
    else:
        sc["near_52wh"] = "fail"

    # institutional demand — accumulation (up/down vol) or a Buy consensus
    if accumulation is None and not consensus:
        sc["institutional"] = "pending"
    elif (accumulation is not None and accumulation > 1.0) or consensus == "Buy":
        sc["institutional"] = "pass"
        pts += W_INST
    else:
        sc["institutional"] = "fail"

    # not yet measurable — shown, never faked
    sc["roic"] = "pending"
    sc["moat"] = "pending"
    sc["runway"] = "pending"

    score = int(round(pts))
    return GrowthCandidate(
        symbol=symbol,
        sector=sector or fund.get("sector"),
        last_price=round(last, 2),
        stage2=stage2,
        rs_vs_spy=rs_vs_spy,
        pct_off_52wh=pct_off_52wh,
        accumulation=accumulation,
        rev_growth_pct=rev,
        rev_accelerating=rev_acc,
        eps_growth_pct=eps,
        gross_margin_pct=gm,
        consensus=consensus,
        scorecard=sc,
        score=score,
        grade=_grade(score),
    )


def rank_growth(cands: list[GrowthCandidate], top_n: int = 25) -> list[GrowthCandidate]:
    """Highest growth-leader score first; assign 1-based rank."""
    ordered = sorted(cands, key=lambda c: c.score, reverse=True)[:top_n]
    for i, c in enumerate(ordered, start=1):
        c.rank = i
    return ordered
