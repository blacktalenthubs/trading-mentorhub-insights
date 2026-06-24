"""Emerging Leaders screener — the weekly themed discovery scout (#64-O).

Finds the names *starting* to move INSIDE the sectors the user already trades — the
next MU / SNDK at the base, not mid-move. The discovery sibling of growth_screener.py
(M, the proven leaders): O catches them young, M holds the winners.

"Emerging" = the intersection of four measurable conditions, each a transparent ✓/✗:
  1. Stage 1→2 turn  — breaking out of a base above a turning 30w-proxy MA, NOT extended
  2. RS vs SPY       — outperforming the index (the leadership tell)
  3. Volume surge    — recent volume expanding vs its own average (accumulation)
  4. Sector tailwind — the name's theme is leading (sector return positive)

Pure + deterministic like growth_screener.py: takes already-fetched DAILY bars + a
sector-return map and returns a scored candidate. DB orchestration (fetch + persist)
lives in api/app/services/screener_service.py. Grade-and-show — a name that fails a
criterion still appears, graded down; never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd

# Themed candidate pools — the universe is the sectors the user trades, EXTENDED with
# names not necessarily on their watchlist (that's the discovery). The sector tag comes
# for free. This is the seed list; Sub-spec O Phase-1 keeps it here (admin-tunable in
# Settings later — manageable over hardcoded). Edit to tune.
EMERGING_SECTORS: dict[str, tuple[str, ...]] = {
    "Memory":      ("MU", "SNDK", "WDC", "STX"),
    "Chips":       ("NVDA", "AVGO", "MRVL", "CRDO", "UCTT", "ALAB", "ONTO", "AEHR", "AMD", "QCOM"),
    "Quantum":     ("IONQ", "RGTI", "QBTS", "QUBT"),
    "Space":       ("RKLB", "LUNR", "RDW", "ASTS"),
    "Robotics":    ("OUST", "SERV", "RR", "NVTS"),
    "Networking":  ("ANET", "CRDO", "CIEN", "COHR"),
    "Optics":      ("AAOI", "LITE", "POET"),
    "Cloud":       ("CRWV", "NBIS", "IREN", "APLD"),
    "AI Software": ("PLTR", "NET", "DDOG", "MDB", "AI", "BBAI"),
    "Power/Nuclear": ("VST", "CEG", "OKLO", "SMR", "NNE"),
}


def universe_with_sectors() -> list[tuple[str, str]]:
    """Flatten the themed pools to (symbol, sector), de-duped (first sector wins)."""
    seen: dict[str, str] = {}
    for sector, syms in EMERGING_SECTORS.items():
        for s in syms:
            seen.setdefault(s.upper(), sector)
    return sorted(seen.items())


MIN_BARS_E = 160        # ~150 (30wMA proxy) + headroom
RS_WINDOW = 63          # ~3 months of sessions for the relative-strength read
HI_WINDOW = 252         # 52-week high context
VOL_FAST = 5            # recent-volume window
VOL_SLOW = 50           # baseline-volume window
EXTENDED_MULT = 1.30    # > 30% above the 30w-proxy MA = late, not "emerging"

# Criterion weights (sum to 100). The four emergence conditions, nothing else.
W_STAGE = 30.0          # Stage 1→2 turn (the early catch)
W_RS = 25.0             # relative-strength leadership vs SPY
W_VOL = 25.0            # volume surge (accumulation)
W_SECTOR = 20.0         # sector tailwind


@dataclass
class EmergingCandidate:
    symbol: str
    sector: str
    last_price: float
    stage_turn: bool
    fresh_cross: bool                 # was below the 30w-proxy within ~20 sessions
    rs_vs_spy: float
    vol_surge: Optional[float]        # mean(last 5d vol) / mean(50d vol)
    sector_ret: Optional[float]       # the sector's avg RS-window return (tailwind)
    pct_off_52wh: Optional[float]     # context only (leaders run toward highs)
    scorecard: dict                   # per-criterion "pass"|"fail"|"pending"
    why: str                          # one-line "why now" for the card
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


def name_return(daily: Optional[pd.DataFrame]) -> Optional[float]:
    """% return over RS_WINDOW sessions — used to aggregate sector tailwind upstream."""
    if daily is None or daily.empty or "Close" not in daily:
        return None
    closes = daily["Close"].astype(float)
    if len(closes) <= RS_WINDOW:
        return None
    last = _lastf(closes)
    prior = float(closes.iloc[-(RS_WINDOW + 1)])
    return (last / prior - 1) * 100 if (last and prior) else None


def evaluate_emerging(
    symbol: str,
    sector: str,
    daily: Optional[pd.DataFrame],
    spy_ret_window: float,
    sector_ret: Optional[float],
) -> Optional[EmergingCandidate]:
    """Score one symbol on the four emergence conditions. Returns None only on
    insufficient data — a name that fails a criterion still appears, graded down."""
    if daily is None or daily.empty or "Close" not in daily or len(daily) < MIN_BARS_E:
        return None
    closes = daily["Close"].astype(float)
    vols = daily["Volume"].astype(float) if "Volume" in daily else None
    n = len(closes)
    last = _lastf(closes)
    if last is None or last <= 0:
        return None

    # ── 1. Stage 1→2 turn ────────────────────────────────────────────────────
    # Above a turning 30w-proxy MA (sma150), short-term trend up (sma50>sma150),
    # but NOT extended (≤30% above) — the catch at the base, not mid-move. "Fresh"
    # when price was below the MA within the last ~20 sessions (the actual turn).
    sma50 = closes.rolling(50).mean()
    sma150 = closes.rolling(150).mean()
    s50, s150 = _lastf(sma50), _lastf(sma150)
    ma150_turning = n >= 161 and float(sma150.iloc[-1]) >= float(sma150.iloc[-11])
    above = s150 is not None and last > s150
    not_extended = s150 is not None and last <= s150 * EXTENDED_MULT
    short_up = s50 is not None and s150 is not None and s50 >= s150
    fresh_cross = bool(
        s150 is not None and n >= 170
        and (closes.iloc[-20:] < sma150.iloc[-20:]).any()
    )
    stage_turn = bool(above and not_extended and ma150_turning and short_up)

    # ── 2. RS vs SPY ─────────────────────────────────────────────────────────
    ret_window = (last / float(closes.iloc[-(RS_WINDOW + 1)]) - 1) * 100 if n > RS_WINDOW else 0.0
    rs_vs_spy = round(ret_window - spy_ret_window, 1)

    # ── 3. Volume surge ──────────────────────────────────────────────────────
    vol_surge: Optional[float] = None
    if vols is not None and n >= VOL_SLOW:
        fast = float(vols.iloc[-VOL_FAST:].mean())
        slow = float(vols.iloc[-VOL_SLOW:].mean())
        vol_surge = round(fast / slow, 2) if slow > 0 else None

    # context
    hi = float(closes.iloc[-HI_WINDOW:].max()) if n >= HI_WINDOW else float(closes.max())
    pct_off_52wh = round((hi - last) / hi * 100, 1) if hi else None

    # ── score ────────────────────────────────────────────────────────────────
    sc: dict = {}
    pts = 0.0

    sc["stage_turn"] = "pass" if stage_turn else "fail"
    if stage_turn:
        pts += W_STAGE if fresh_cross else W_STAGE * 0.7  # fresh turn worth more

    if rs_vs_spy > 0:
        sc["rs_leadership"] = "pass"
        pts += min(rs_vs_spy, 20.0) / 20.0 * W_RS
    else:
        sc["rs_leadership"] = "fail"

    if vol_surge is None:
        sc["vol_surge"] = "pending"
    elif vol_surge >= 1.5:
        sc["vol_surge"] = "pass"
        pts += W_VOL if vol_surge >= 2.5 else W_VOL * 0.6
    else:
        sc["vol_surge"] = "fail"

    if sector_ret is None:
        sc["sector_tailwind"] = "pending"
    elif sector_ret > 0:
        sc["sector_tailwind"] = "pass"
        pts += W_SECTOR
    else:
        sc["sector_tailwind"] = "fail"

    score = int(round(pts))

    # ── one-line "why now" from the passing criteria ─────────────────────────
    bits: list[str] = []
    if stage_turn:
        bits.append("Stage 1→2 turn" if fresh_cross else "early Stage 2")
    if vol_surge and vol_surge >= 1.5:
        bits.append(f"{vol_surge:.1f}× base vol")
    if rs_vs_spy > 0:
        bits.append(f"+{rs_vs_spy:.0f}% vs SPY")
    if sector_ret is not None and sector_ret > 0:
        bits.append(f"{sector} leads")
    why = " · ".join(bits) if bits else f"{sector} — building, not yet confirmed"

    return EmergingCandidate(
        symbol=symbol,
        sector=sector,
        last_price=round(last, 2),
        stage_turn=stage_turn,
        fresh_cross=fresh_cross,
        rs_vs_spy=rs_vs_spy,
        vol_surge=vol_surge,
        sector_ret=round(sector_ret, 1) if sector_ret is not None else None,
        pct_off_52wh=pct_off_52wh,
        scorecard=sc,
        why=why,
        score=score,
        grade=_grade(score),
    )


def rank_emerging(cands: list[EmergingCandidate], top_n: int = 5) -> list[EmergingCandidate]:
    """Highest emergence score first; assign 1-based rank. Default ≤5 (a tap, not a board)."""
    ordered = sorted(cands, key=lambda c: c.score, reverse=True)[:top_n]
    for i, c in enumerate(ordered, start=1):
        c.rank = i
    return ordered
