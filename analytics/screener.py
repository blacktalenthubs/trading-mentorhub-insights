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

import datetime as _dt
from dataclasses import dataclass, field
from datetime import time as dt_time
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import pandas as pd

ET_ZONE = ZoneInfo("America/New_York")

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
    grade: str = "C"           # A/B/C from rvol + intraday VWAP slope (compute_grade)
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
            "grade": self.grade,
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


# Static fallback universe — liquid US large/mid caps. Used when the dynamic
# yfinance screener returns nothing (e.g. yf.screen is blocked from cloud IPs).
# Per-symbol daily data still comes from the working fetch_ohlc path.
STATIC_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "ORCL", "AMD",
    "ADBE", "CRM", "NFLX", "INTC", "QCOM", "TXN", "MU", "AMAT", "NOW", "INTU",
    "IBM", "CSCO", "PLTR", "SNOW", "SHOP", "UBER", "ABNB", "PYPL", "SQ", "COIN",
    "DELL", "HPQ", "ANET", "PANW", "CRWD", "FTNT", "DDOG", "NET", "SMCI", "MRVL",
    "JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "AXP", "BLK", "V",
    "MA", "BRK-B", "UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO", "ABT",
    "BMY", "AMGN", "GILD", "CVS", "MDT", "ISRG", "WMT", "COST", "HD", "LOW",
    "TGT", "NKE", "SBUX", "MCD", "PG", "KO", "PEP", "DIS", "CMCSA", "T",
    "VZ", "XOM", "CVX", "COP", "SLB", "OXY", "BA", "CAT", "GE", "HON",
    "UPS", "RTX", "LMT", "DE", "MMM", "F", "GM", "RIVN", "LCID", "DKNG",
    "ROKU", "PINS", "SNAP", "SOFI", "HOOD", "MARA", "RIOT", "CCL", "AAL", "DAL",
    "PDD", "BABA", "NIO", "ON", "ASML", "TSM", "ARM", "WDAY", "TEAM", "ZS",
)


def static_universe_rows() -> list[UniverseRow]:
    """Pre-vetted large-cap rows (sentinel cap/price; real prices come from the
    per-symbol scan). Bypasses the floor filter — these are all clearly liquid."""
    return [UniverseRow(symbol=s, market_cap=5e10, last_price=100.0, avg_dollar_vol=1e8, sector=None)
            for s in STATIC_UNIVERSE]


# Curated US mega-caps (all comfortably > $100B). The swing screener scans THIS
# list directly so it (a) targets mega caps and (b) doesn't depend on the dynamic
# universe build, which can be blocked on cloud IPs.
MEGA_CAP_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO", "LLY", "JPM",
    "WMT", "V", "MA", "ORCL", "UNH", "XOM", "COST", "HD", "PG", "JNJ",
    "NFLX", "BAC", "ABBV", "CRM", "KO", "CVX", "AMD", "PEP", "WFC", "CSCO",
    "ADBE", "MCD", "ACN", "LIN", "ABT", "IBM", "GE", "MRK", "ISRG", "INTU",
    "TXN", "QCOM", "DIS", "CAT", "GS", "AXP", "VZ", "AMGN", "RTX", "PFE",
    "NOW", "UBER", "BLK", "HON", "LOW", "PLTR", "ANET", "MS", "DE", "MU",
)


def mega_cap_rows() -> list[UniverseRow]:
    """The mega-cap pool for the swing screener (sentinel cap; real prices from the scan)."""
    return [UniverseRow(symbol=s, market_cap=2e11, last_price=100.0, avg_dollar_vol=1e8, sector=None)
            for s in MEGA_CAP_UNIVERSE]


# Curated liquid small/mid caps + notable recent IPOs (momentum names). The baseline
# small-cap pool — unioned with Alpaca most-actives when that endpoint is available.
# Quality gates (price ≥ $2, real $-volume) are applied per-symbol at scan time.
SMALL_CAP_UNIVERSE: tuple[str, ...] = (
    "RKLB", "SOFI", "HOOD", "DKNG", "AFRM", "RIVN", "LCID", "CHPT", "PLUG", "RUN",
    "MARA", "RIOT", "CLSK", "IONQ", "RGTI", "QBTS", "SMR", "OKLO", "ASTS", "ACHR",
    "JOBY", "LUNR", "RDW", "SOUN", "BBAI", "AI", "PATH", "GTLB", "S", "CFLT",
    "FROG", "BRZE", "AMPL", "ESTC", "DOCN", "FSLY", "U", "RBLX", "DUOL", "UPST",
    "LMND", "OPEN", "RDFN", "CVNA", "CHWY", "ETSY", "W", "PINS", "SNAP", "BMBL",
    "RDDT", "CART", "CAVA", "BIRK", "ALAB", "ENVX", "QS", "EOSE", "FLNC", "NVAX",
    "BYND", "PTON", "FUBO", "PSNY", "RIG", "NCLH", "LYFT", "GRAB", "NU", "ZIM",
    "DNA", "SE", "PARA", "WBD", "GME", "AMC", "KSS", "CCL", "AAL", "UAL",
)


def small_cap_rows() -> list[UniverseRow]:
    """The curated small-cap pool (sentinel cap/price; real prices from the scan)."""
    return [UniverseRow(symbol=s, market_cap=2e9, last_price=20.0, avg_dollar_vol=5e7, sector=None)
            for s in SMALL_CAP_UNIVERSE]


def build_universe(
    market_cap_floor: float = DEFAULT_MARKET_CAP_FLOOR,
    price_floor: float = DEFAULT_PRICE_FLOOR,
    dollar_vol_floor: float = DEFAULT_DOLLAR_VOL_FLOOR,
    fetcher: Optional[Callable[[float], list[UniverseRow]]] = None,
) -> list[UniverseRow]:
    """Build the capped universe (FR-1). Tries the dynamic ``fetcher`` (yfinance
    screener) and applies the floors; if that yields too few names (source blocked
    or empty), falls back to the static large-cap list so scans always have a pool.
    """
    if fetcher is None:
        fetcher = _yfinance_universe_fetcher
    try:
        candidates = fetcher(market_cap_floor)
    except Exception:
        candidates = []
    rows = filter_universe(candidates, market_cap_floor, price_floor, dollar_vol_floor)
    if len(rows) < 50:
        rows = static_universe_rows()
    return rows


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

def is_market_open(now: _dt.datetime | None = None) -> bool:
    """Regular US trading hours, Mon–Fri (no holiday calendar in v1). Pure + injectable.

    A tz-aware ``now`` is converted to ET; a naive ``now`` is assumed already ET.
    """
    if now is None:
        now = _dt.datetime.now(ET_ZONE)
    elif now.tzinfo is not None:
        now = now.astimezone(ET_ZONE)
    if now.weekday() >= 5:
        return False
    return RTH_OPEN <= now.time() <= RTH_CLOSE


def effective_settings(defaults: dict, overrides: Optional[dict]) -> dict:
    """Overlay a user's per-user overrides (FR-6) on the global defaults.
    Only non-None override values win; everything else falls back to defaults.
    """
    out = dict(defaults)
    for k, v in (overrides or {}).items():
        if v is not None:
            out[k] = v
    return out


def apply_user_view(
    entries: list["InPlayEntry"],
    top_n: Optional[int] = None,
    market_cap_floor: Optional[float] = None,
) -> list["InPlayEntry"]:
    """Per-user VIEW over the global snapshot (FR-6): tighten the cap and/or trim
    the list. Does not recompute — just narrows what this user sees.
    """
    out = entries
    if market_cap_floor is not None:
        out = [e for e in out if e.market_cap >= market_cap_floor]
    if top_n is not None:
        out = out[: max(0, top_n)]
    return out


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
# Swing screener — market-wide daily-bar setups (Trend + MA defense)
# ---------------------------------------------------------------------------

@dataclass
class SwingCandidate:
    symbol: str
    last_price: float
    ret_20d: float        # 20-day % return (momentum)
    rs_vs_spy: float      # ret_20d minus SPY's 20-day return
    above_ema21: bool
    above_ema50: bool
    ema_stacked: bool     # 21 > 50 > 200
    ma_defense: bool      # recent tag-and-hold of the 21/50 EMA
    setup: Optional[dict] = None  # {pattern, entry, stop, target, conviction} when it qualifies
    market_cap: float = 0.0
    sector: Optional[str] = None
    vol_ratio: float = 1.0        # today's daily volume vs 20-day average
    close_strength: float = 0.5   # close location in today's range (CLV): 1=closed at high, 0=at low
    grade: str = "C"             # A/B/C — volume + close-strength (see swing_grade)
    rank: int = 0

    def to_dict(self) -> dict:
        return {
            "rank": self.rank, "symbol": self.symbol, "last_price": round(self.last_price, 2),
            "ret_20d": round(self.ret_20d, 1), "rs_vs_spy": round(self.rs_vs_spy, 1),
            "above_ema21": self.above_ema21, "above_ema50": self.above_ema50,
            "ema_stacked": self.ema_stacked, "ma_defense": self.ma_defense,
            "setup": self.setup, "market_cap": self.market_cap, "sector": self.sector,
            "vol_ratio": round(self.vol_ratio, 2),
            "close_strength": round(self.close_strength, 2), "grade": self.grade,
        }


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def vol_grade(vol_ratio: Optional[float]) -> str:
    """Vol-only A/B/C grade for daily-timeframe setups (no intraday slope).
    A = today's volume ≥ 2× the 20-day average, B ≥ 1.3×, else C. Used by the
    AI Best Setups badge (no per-bar OHLC handy there)."""
    if vol_ratio is None:
        return "C"
    if vol_ratio >= 2.0:
        return "A"
    if vol_ratio >= 1.3:
        return "B"
    return "C"


# Close-strength gate for the swing grade. CLV ≥ this = closed in the top third
# of the day's range (buyers defended into the close — the daily analog of a
# rising VWAP). Mirrors the In-Play grade's slope gate.
SWING_CLOSE_GATE = 0.66
SWING_VOL_GATE = 2.0


def swing_grade(vol_ratio: Optional[float], close_strength: Optional[float]) -> str:
    """Two-gate A/B/C for daily swing setups — the daily analog of the In-Play
    grade (volume + VWAP slope). The second gate here is *close strength* (close
    location in the bar's range, CLV): did buyers defend the level into the
    close, or did it close on its lows?

      A = heavy volume (≥ 2× avg)  AND  strong close (CLV ≥ 0.66, top third)
      B = exactly one gate passes
      C = neither

    A volume spike that closes on its lows (distribution into the MA) now grades
    B, not A — heavy volume alone no longer earns an A without buyers defending."""
    vol_pass = vol_ratio is not None and vol_ratio >= SWING_VOL_GATE
    close_pass = close_strength is not None and close_strength >= SWING_CLOSE_GATE
    passes = int(vol_pass) + int(close_pass)
    if passes == 2:
        return "A"
    if passes == 1:
        return "B"
    return "C"


def swing_signals(
    daily: pd.DataFrame, spy_ret_20d: float = 0.0, *,
    symbol: str = "", market_cap: float = 0.0, sector: Optional[str] = None,
    small_cap: bool = False,
) -> Optional[SwingCandidate]:
    """Evaluate DAILY bars for a 'closing right at a key MA' swing setup.

    A swing entry is a pullback that holds a key moving average — price closes
    *at* the 20 / 50 (/ 200) EMA (tested it intrabar, closed within a tight band),
    in an uptrend, NOT extended. Stop sits just below that MA → tight R:R.

    ``small_cap=True`` relaxes for small caps / recent IPOs: 20 & 50 EMA only (no
    200-day history required), shorter minimum history.
    """
    min_bars = 50 if small_cap else 60
    if daily is None or daily.empty or "Close" not in daily.columns or len(daily) < min_bars:
        return None
    c = daily["Close"]
    last = float(c.iloc[-1])
    low = float(daily["Low"].iloc[-1])
    high = float(daily["High"].iloc[-1])
    e20, e50 = float(_ema(c, 20).iloc[-1]), float(_ema(c, 50).iloc[-1])
    e200 = float(_ema(c, 200).iloc[-1]) if len(c) >= 200 else None
    ret20 = (last / float(c.iloc[-21]) - 1.0) * 100.0 if len(c) > 21 else 0.0
    rs = ret20 - spy_ret_20d

    if small_cap:
        uptrend = e20 > e50 and last > e50                      # short-term uptrend, no 200 needed
        stacked = e20 > e50
        candidate_mas = (("20 EMA", e20), ("50 EMA", e50))
    else:
        uptrend = e200 is not None and e50 > e200 and last > e200
        stacked = e200 is not None and e20 > e50 > e200
        candidate_mas = (("20 EMA", e20), ("50 EMA", e50), ("200 EMA", e200)) if e200 is not None else (("20 EMA", e20), ("50 EMA", e50))

    # Which key MA is price closing JUST AT? Nearest first. "At" = today's low tested
    # it (within 1%) AND the close sits in a tight band (-1% to +2%) around it.
    tested = None  # (name, ma_value)
    for name, ma in candidate_mas:
        if ma is not None and low <= ma * 1.01 and -0.01 <= (last - ma) / ma <= 0.02:
            tested = (name, ma)
            break

    setup = None
    if tested is not None and uptrend:
        name, ma = tested
        stop = round(min(low, ma) * 0.985, 2)     # just below the held MA / bar low → tight
        entry = round(last, 2)
        risk = max(0.01, entry - stop)
        setup = {
            "pattern": f"{name} hold", "entry": entry, "stop": stop,
            "target": round(entry + risk * 3.0, 2),   # ~3R, like a clean MA-pullback entry
            "conviction": "High" if (stacked and name == "20 EMA") else "Moderate",
        }

    # Two-gate daily grade: volume (participation) + close strength (direction).
    vol = daily["Volume"]
    avg_vol = float(vol.tail(20).mean()) if len(vol) >= 20 else float(vol.mean())
    vol_ratio = (float(vol.iloc[-1]) / avg_vol) if avg_vol > 0 else 1.0
    # Close location value: where the close sits in today's range (1=high, 0=low).
    # Daily analog of VWAP slope — did buyers defend the MA into the close?
    close_strength = ((last - low) / (high - low)) if high > low else 0.5
    grade = swing_grade(vol_ratio, close_strength)

    return SwingCandidate(
        symbol=symbol, last_price=last, ret_20d=ret20, rs_vs_spy=rs,
        above_ema21=last > e20, above_ema50=last > e50, ema_stacked=stacked,
        ma_defense=tested is not None, setup=setup, market_cap=market_cap, sector=sector,
        vol_ratio=vol_ratio, close_strength=close_strength, grade=grade,
    )


def rank_swing(cands: list[SwingCandidate], top_n: int = DEFAULT_TOP_N) -> list[SwingCandidate]:
    """Keep only qualifying setups; rank by relative strength desc; assign rank."""
    qualified = sorted([c for c in cands if c.setup], key=lambda c: c.rs_vs_spy, reverse=True)[: max(0, top_n)]
    for i, c in enumerate(qualified, start=1):
        c.rank = i
    return qualified


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

def _num(v) -> float:
    """Coerce a possibly-None/missing refine value to a number (None-safe predicates)."""
    return v if isinstance(v, (int, float)) else 0.0


def _is_momentum_long(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("above_ema50") and r.get("above_vwap")
                and 50 <= _num(r.get("rsi")) <= 70 and _num(r.get("rs_vs_spy")) > 0)


def _is_pullback(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("above_ema50") and 35 <= _num(r.get("rsi")) <= 50)


def _is_breakout(e: InPlayEntry) -> bool:
    r = e.refine
    return bool(r.get("near_20d_high") and e.rvol >= 2 and r.get("above_vwap"))


def _is_short(e: InPlayEntry) -> bool:
    r = e.refine
    return bool((not r.get("above_ema50")) and (not r.get("above_vwap"))
                and 30 <= _num(r.get("rsi")) <= 50)


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
