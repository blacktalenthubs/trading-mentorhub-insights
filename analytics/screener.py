"""In-Play Volume Screener — spec 62.

Curation layer (NOT new analysis): cap a liquid universe, rank by a REAL
time-of-day-normalized relative volume during market hours, scan the shortlist
with the existing ``signal_engine`` (read-only), and apply optional style presets.

Design notes
------------
* The shared ``analytics.intraday_data.compute_rvol`` is currently a placeholder
  that resolves to ~1.0 for every symbol, so it cannot rank. This module computes
  its own ``relative_volume`` to avoid touching alert-adjacent code (Constitution
  §1 — protect business logic). Replacing the shared stub is a separate cleanup.
* Setup detection reuses ``signal_engine.analyze_symbol`` read-only; this module
  never modifies any protected file.
* The pure functions below take already-aggregated inputs (or injected providers)
  so they are deterministic and unit-testable without live market data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time as dt_time
from typing import Callable, Optional

import pandas as pd

# --- defaults (mirror api/app/config.py SCREENER_*) ---
DEFAULT_MARKET_CAP_FLOOR = 2_000_000_000.0
DEFAULT_PRICE_FLOOR = 5.0
DEFAULT_DOLLAR_VOL_FLOOR = 20_000_000.0
DEFAULT_TOP_N = 30

# Regular US trading session (ET)
RTH_OPEN = dt_time(9, 30)
RTH_CLOSE = dt_time(16, 0)
_RTH_SECONDS = (16 - 9) * 3600 - 30 * 60  # 6.5h = 23400s


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass
class UniverseRow:
    symbol: str
    market_cap: float
    last_price: float
    avg_dollar_vol: float
    sector: Optional[str] = None


@dataclass
class InPlayEntry:
    symbol: str
    last_price: float
    pct_change: float
    rvol: float
    dollar_vol: float
    market_cap: float
    sector: Optional[str] = None
    direction: str = "neutral"  # long | short | neutral
    setup: Optional[dict] = None
    refine: dict = field(default_factory=dict)
    rank: int = 0

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "symbol": self.symbol,
            "last_price": round(self.last_price, 4),
            "pct_change": round(self.pct_change, 4),
            "rvol": round(self.rvol, 3),
            "dollar_vol": round(self.dollar_vol, 2),
            "market_cap": self.market_cap,
            "sector": self.sector,
            "direction": self.direction,
            "setup": self.setup,
            "refine": self.refine,
        }


# ---------------------------------------------------------------------------
# Layer 1 — universe filtering (pure; the fetch is a thin live adapter)
# ---------------------------------------------------------------------------

def filter_universe(
    rows: list[UniverseRow],
    market_cap_floor: float = DEFAULT_MARKET_CAP_FLOOR,
    price_floor: float = DEFAULT_PRICE_FLOOR,
    dollar_vol_floor: float = DEFAULT_DOLLAR_VOL_FLOOR,
) -> list[UniverseRow]:
    """Keep only liquid, tradable names above all three floors (FR-1)."""
    return [
        r for r in rows
        if r.market_cap >= market_cap_floor
        and r.last_price >= price_floor
        and r.avg_dollar_vol >= dollar_vol_floor
    ]


def build_universe(
    market_cap_floor: float = DEFAULT_MARKET_CAP_FLOOR,
    price_floor: float = DEFAULT_PRICE_FLOOR,
    dollar_vol_floor: float = DEFAULT_DOLLAR_VOL_FLOOR,
    fetcher: Optional[Callable[[float], list[UniverseRow]]] = None,
) -> list[UniverseRow]:
    """Build the capped universe (FR-1). ``fetcher`` returns candidate rows for a
    given market-cap floor (default: yfinance adapter); filtering is then applied
    locally so price/$-volume floors are enforced regardless of source.
    """
    if fetcher is None:
        fetcher = _yfinance_universe_fetcher
    candidates = fetcher(market_cap_floor)
    return filter_universe(candidates, market_cap_floor, price_floor, dollar_vol_floor)


def _yfinance_universe_fetcher(market_cap_floor: float) -> list[UniverseRow]:  # pragma: no cover - live I/O
    """Live Layer-1 adapter — yfinance equity screener.

    Field names drift across yfinance 0.2.x; isolated here so a rename is a
    one-line fix (see research.md R1). Returns candidate UniverseRow list.
    """
    import yfinance as yf

    rows: list[UniverseRow] = []
    q = yf.EquityQuery("and", [
        yf.EquityQuery("gt", ["intradaymarketcap", market_cap_floor]),
        yf.EquityQuery("eq", ["region", "us"]),
    ])
    size = 250
    offset = 0
    while True:
        res = yf.screen(q, offset=offset, size=size, sortField="dayvolume", sortAsc=False)
        quotes = (res or {}).get("quotes", [])
        if not quotes:
            break
        for qd in quotes:
            price = qd.get("regularMarketPrice") or 0.0
            vol = qd.get("regularMarketVolume") or qd.get("averageDailyVolume3Month") or 0.0
            rows.append(UniverseRow(
                symbol=qd.get("symbol", ""),
                market_cap=float(qd.get("marketCap") or 0.0),
                last_price=float(price),
                avg_dollar_vol=float(price) * float(vol),
                sector=qd.get("sector"),
            ))
        offset += size
        if len(quotes) < size or offset >= 2000:
            break
    return rows


# ---------------------------------------------------------------------------
# Layer 2 — relative volume + ranking (pure)
# ---------------------------------------------------------------------------

def session_fraction(now_et: dt_time) -> float:
    """Fraction of the RTH session elapsed at ``now_et`` ∈ [0, 1]."""
    if now_et <= RTH_OPEN:
        return 0.0
    if now_et >= RTH_CLOSE:
        return 1.0
    elapsed = (now_et.hour * 3600 + now_et.minute * 60 + now_et.second) - (9 * 3600 + 30 * 60)
    return max(0.0, min(1.0, elapsed / _RTH_SECONDS))


def relative_volume(today_cum_vol: float, avg_daily_vol: float, session_frac: float) -> float:
    """Time-of-day-normalized RVOL (FR-2). Today's cumulative volume vs the volume
    we'd *expect* by this point in the session. >1 = unusually active. Robust to a
    zero/early-session denominator.
    """
    expected = avg_daily_vol * max(session_frac, 1e-6)
    if expected <= 0:
        return 1.0
    return float(today_cum_vol) / float(expected)


def rank_in_play(entries: list[InPlayEntry], top_n: int = DEFAULT_TOP_N) -> list[InPlayEntry]:
    """Rank by RVOL desc, dollar-volume tiebreaker; return top-N with rank set (FR-2)."""
    ranked = sorted(entries, key=lambda e: (e.rvol, e.dollar_vol), reverse=True)[: max(0, top_n)]
    for i, e in enumerate(ranked, start=1):
        e.rank = i
    return ranked


# ---------------------------------------------------------------------------
# Setup detection — reuse signal_engine read-only (FR-4)
# ---------------------------------------------------------------------------

# Statuses that represent an actionable setup (vs. "BROKEN" / no setup).
_SETUP_STATUSES = {"AT SUPPORT", "PULLBACK WATCH"}


def _result_to_setup(result) -> Optional[dict]:
    """Map a signal_engine SignalResult → setup dict, or None when no setup."""
    if result is None:
        return None
    status = getattr(result, "support_status", "") or ""
    if status not in _SETUP_STATUSES:
        return None  # listed as a mover, but "no setup"
    return {
        "pattern": getattr(result, "support_label", "") or getattr(result, "pattern", ""),
        "entry": getattr(result, "entry", None),
        "stop": getattr(result, "stop", None),
        "target": getattr(result, "target_1", None),
        "conviction": getattr(result, "score_label", "") or "",
        "score": getattr(result, "score", 0),
        "bias": getattr(result, "bias", ""),
    }


def scan_setups(
    entries: list[InPlayEntry],
    hist_provider: Callable[[str], Optional[pd.DataFrame]],
    analyzer: Optional[Callable] = None,
) -> list[InPlayEntry]:
    """Attach a detected setup (or None) to each entry by calling the existing
    pattern analyzer read-only. ``hist_provider(symbol)`` yields the symbol's
    history; ``analyzer`` defaults to ``signal_engine.analyze_symbol``.
    """
    if analyzer is None:
        from analytics.signal_engine import analyze_symbol as analyzer  # read-only reuse
    for e in entries:
        hist = hist_provider(e.symbol)
        result = analyzer(hist, e.symbol) if hist is not None else None
        e.setup = _result_to_setup(result)
    return entries


# ---------------------------------------------------------------------------
# Layer 3 — refine filters / presets (pure, direction-aware) — FR-9
# ---------------------------------------------------------------------------

def _is_momentum_long(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("above_ema50") and r.get("above_vwap")
                and 50 <= r.get("rsi", 0) <= 70 and r.get("rs_vs_spy", 0) > 0)


def _is_pullback(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("above_ema50") and 35 <= r.get("rsi", 0) <= 50)


def _is_breakout(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("near_20d_high") and e.rvol >= 2 and r.get("above_vwap"))


def _is_short(e: InPlayEntry) -> bool:
    r = e.refine
    return bool((not r.get("above_ema50")) and (not r.get("above_vwap"))
                and 30 <= r.get("rsi", 0) <= 50)


PRESETS: dict[str, dict] = {
    "momentum_long": {"direction": "long", "predicate": _is_momentum_long},
    "pullback": {"direction": "long", "predicate": _is_pullback},
    "breakout": {"direction": "long", "predicate": _is_breakout},
    "short": {"direction": "short", "predicate": _is_short},
    "any": {"direction": "any", "predicate": lambda e: True},
}


def apply_refine_filters(
    entries: list[InPlayEntry],
    preset: str = "any",
    direction: str = "any",
    has_setup: bool = False,
) -> list[InPlayEntry]:
    """Narrow/sort the ranked shortlist by an optional preset (FR-9).

    Direction-aware: a long preset does not delete short setups from existence —
    they remain reachable via the ``short``/``any`` selection (rank order preserved).
    """
    preset_cfg = PRESETS.get(preset, PRESETS["any"])
    out = [e for e in entries if preset_cfg["predicate"](e)]
    if direction != "any":
        out = [e for e in out if e.direction == direction]
    if has_setup:
        out = [e for e in out if e.setup]
    return out
