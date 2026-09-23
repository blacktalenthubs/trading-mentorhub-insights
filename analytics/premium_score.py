"""Premium Desk S2 — the scoring engine. Rank each leveraged ETF for SELLING premium.

Three factors, exactly as specced: IV Rank (is premium rich?), RSI (daily + weekly
timing), key moving-average reclaims (is there a floor under a short put?). They fold
into a 0-100 score for ordering and, more importantly, a RISK TIER — low / med / high —
which is the headline the desk ranks by.

The mental model is the cash-secured put (the MVP side): you collect premium and take
assignment risk. So "risk" here is DIRECTIONAL — how safe is the floor beneath the strike?
  - LOW   rich premium AND a clean uptrend structure (above a rising 200, holding 20/50,
          RSI not stretched). A put you're happy to be assigned.
  - MED   rich premium but stretched or mixed structure — manageable, watch it.
  - HIGH  rich premium BECAUSE the name is in trouble (below the 200, falling/knife RSI).
          Only for aggressive sellers, far OTM.

Premium richness (IV Rank) is the QUALIFY gate; posture sets the tier. Pure & testable:
`score_candidate` takes OHLC frames + the iv_rank dict, does no I/O. Reuses the validated
RSI/MA helpers from support_signals so the math matches the rest of the platform.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from analytics.support_signals import _bounce, _rising, _rsi, _rsi_reversal, _sma, _wick_hold

# --- tunables ----------------------------------------------------------------
QUALIFY_IVR = 50.0     # IV rank at/above this = premium rich enough to sell (classic line)
MIN_HISTORY = 20       # iv_history rows below this → rank not yet trustworthy ("warming")
OVERSOLD = 40.0        # RSI zone shared with the support engine
OVERBOUGHT = 70.0
MA_TOL = 0.01
# Entry-timing thresholds for SELLING a cash-secured put. The best entry is a DIP —
# oversold turning up, or a bounce off a key long-term MA — NOT strength. Selling into a
# high-RSI rip means selling near the top: a pullback assigns you high. So high RSI is a
# RISK, not a plus.
EXTENDED_RSI = 65.0     # at/over this = extended, near the top → the worst CSP entry
LOW_RSI_ROOM = 52.0     # at/under (with intact structure) = room to run, still a fair entry
RECOVER_LOOK = 7        # bars to look back for a recent oversold low we're turning up from
# Suggested short-put distance OTM by tier — safer tier sits closer, riskier further out.
OTM_BY_TIER = {"low": 0.03, "med": 0.05, "high": 0.08}
DTE = 30

# Composite weights — premium is why we're here; ENTRY QUALITY (dip vs extended) is the
# thing we most got wrong before, so it dominates; trend context is the backdrop.
W_IV, W_ENTRY, W_CONTEXT = 0.30, 0.50, 0.20

TRADING_DAYS_SQRT = 252 ** 0.5  # annual IV → 1-day expected move: IV / √252


@dataclass
class PremiumCandidate:
    symbol: str
    theme: str
    price: float
    # factors
    iv: float                    # latest ATM IV (%)
    iv_rank: float               # 0-100 (0 when warming)
    iv_pct: float                # IV percentile sibling
    iv_n: int                    # sessions of history behind the rank
    iv_warming: bool             # history too short to trust the rank yet
    rsi_d: float
    rsi_w: float
    # posture
    above_200: bool
    above_50: bool
    above_20: bool
    reclaim: str = ""            # a key MA reclaimed NOW ("20/50 MA", "200 SMA", "")
    # verdict
    score: float = 0.0           # 0-100 composite (ordering within a tier)
    tier: str = "med"            # low | med | high
    qualifies: bool = False      # IV rich enough to sell now (or warming)
    side: str = "put"            # CSP MVP
    strike: float = 0.0          # suggested short-put strike (tier-scaled OTM)
    dte: int = DTE
    rationale: list[str] = field(default_factory=list)
    # next-session planning (valuable off-hours; prices don't move after close)
    exp_move_pct: float = 0.0    # expected 1-day move from ATM IV (±%)
    exp_move_usd: float = 0.0    # that move in $
    strike_cushion_pct: float = 0.0   # how far the suggested strike sits below spot
    sma20: float = 0.0
    sma50: float = 0.0
    sma200: float = 0.0          # the institutional floor
    floor_dist_pct: float = 0.0  # distance from spot down to the 200 SMA (the real floor)
    earnings_days: int | None = None   # sessions to next earnings (None = unknown)
    earnings_warn: bool = False        # earnings falls inside the option's DTE window


def _recovering(rsi, zone: float = OVERSOLD, look: int = RECOVER_LOOK) -> bool:
    """Turning up off a recent oversold low — the AVGO case. A bar in the last `look`
    dipped under `zone`, RSI is now higher than that low (turning up) and not yet stretched.
    Broader than a strict 1-bar reversal, which misses a bottom put in a few bars ago."""
    if rsi is None or len(rsi) < 3:
        return False
    recent = rsi.iloc[-look:] if len(rsi) >= look else rsi
    lo = float(recent.min())
    cur = float(rsi.iloc[-1])
    return lo < zone and cur > lo and cur < 58.0


def _entry_score(rd, rev_d, rev_w, recovering, bounce_key) -> float:
    """Quality of the moment to SELL a put. Dip/bounce = high; extension = low."""
    v = 50.0
    if rev_d or recovering:
        v += 24          # bouncing off / turning up from a low — the prime entry
    if rev_w:
        v += 8
    if bounce_key:
        v += 20          # tagged a key long-term (50/200) MA and held
    if rd < OVERSOLD:
        v += 6           # sitting in the oversold zone, coiled
    elif rd <= LOW_RSI_ROOM:
        v += 3           # room to run
    if rd >= 60:
        v -= 10          # getting warm
    if rd >= EXTENDED_RSI:
        v -= 26          # extended — selling a put here is selling near the top
    if rd >= OVERBOUGHT + 2:
        v -= 12
    return max(0.0, min(100.0, v))


def _context_score(above200, above50) -> float:
    """Trend backdrop — a dip inside an uptrend (above the 200) is a far better place to be
    assigned than a dip inside a downtrend. Note: we do NOT reward being extended above the
    fast MAs; that's timing, handled by the entry score."""
    v = 50.0
    v += 18 if above200 else -24
    v += 6 if above50 else -4
    return max(0.0, min(100.0, v))


def _tier(above200, extended, turning, bounce_key) -> str:
    """Risk of the CSP ENTRY (not trend strength).
      HIGH  extended (RSI near the top → selling into a rip) OR a falling knife
            (below the 200 with nothing turning up).
      LOW   a real dip entry — turning up off oversold, or a 50/200 bounce.
      MED   the neutral middle: intact structure, RSI mid-range, no bounce."""
    good_entry = turning or bounce_key
    if extended:
        return "high"                       # near the top — the worst place to sell a put
    if not above200 and not good_entry:
        return "high"                       # below the 200 and not turning up → knife
    if good_entry:
        return "low"
    return "med"


def score_candidate(daily: pd.DataFrame, weekly: pd.DataFrame, symbol: str,
                    iv: dict | None, *, theme: str = "") -> PremiumCandidate | None:
    """Score one ETF. `iv` is the iv_rank() dict (or None if no history yet)."""
    if daily is None or weekly is None or len(daily) < 20 or len(weekly) < 3:
        return None
    dc = daily["Close"].astype(float)
    do = daily["Open"].astype(float)
    dl = daily["Low"].astype(float)
    c, o, l = float(dc.iloc[-1]), float(do.iloc[-1]), float(dl.iloc[-1])

    rsi_d, rsi_w = _rsi(dc), _rsi(weekly["Close"].astype(float))
    rd, rw = float(rsi_d.iloc[-1]), float(rsi_w.iloc[-1])
    rev_d, rev_w = _rsi_reversal(rsi_d, OVERSOLD), _rsi_reversal(rsi_w, OVERSOLD)

    s20, s50, s200 = _sma(dc, 20), _sma(dc, 50), _sma(dc, 200)
    r20, r50 = _rising(dc, 20), _rising(dc, 50)
    above20 = s20 is not None and c > s20
    above50 = s50 is not None and c > s50
    above200 = s200 is not None and c > s200

    # Entry timing — the thing that most drives the tier.
    recovering = _recovering(rsi_d)                        # turning up off a recent oversold low
    bounce50 = _bounce(o, l, c, s50, MA_TOL)
    bounce200 = _bounce(o, l, c, s200, MA_TOL)
    bounce_key = bounce50 or bounce200                     # a KEY long-term MA bounce (50/200)
    turning = rev_d or rev_w or recovering
    extended = rd >= EXTENDED_RSI                          # RSI near the top → don't sell here

    # A key MA bounced RIGHT NOW (open-above wick-hold) — for the rationale label.
    reclaim = "200 SMA" if bounce200 else ("50 MA" if bounce50 else "")

    # IV factor.
    if iv is None:
        iv_val, iv_rank, iv_pct, iv_n = 0.0, 0.0, 0.0, 0
        warming = True
    else:
        iv_val, iv_rank, iv_pct, iv_n = iv["iv"], iv["rank"], iv["percentile"], iv["n"]
        warming = iv_n < MIN_HISTORY

    entry = _entry_score(rd, rev_d, rev_w, recovering, bounce_key)
    context = _context_score(above200, above50)
    # While warming, the rank is meaningless → neutral premium term.
    iv_compo = 50.0 if warming else iv_rank
    score = round(W_IV * iv_compo + W_ENTRY * entry + W_CONTEXT * context, 1)

    tier = _tier(above200, extended, turning, bounce_key)
    qualifies = warming or iv_rank >= QUALIFY_IVR
    otm = OTM_BY_TIER[tier]
    strike = round(c * (1 - otm), 2)

    # Human rationale — lead with WHY THIS IS (or isn't) a good moment to sell a put.
    rat: list[str] = []
    if extended:
        rat.append(f"extended — daily RSI {rd:.0f}, near the top")
    elif rev_d or recovering:
        rat.append(f"turning up off oversold (RSI {rd:.0f})")
    elif bounce_key:
        rat.append(f"bounce off {reclaim}")
    elif rd < OVERSOLD:
        rat.append(f"oversold — daily RSI {rd:.0f} (watch for the turn)")
    else:
        rat.append(f"daily RSI {rd:.0f}")
    rat.append(f"{'above' if above200 else 'below'} 200 SMA" + (", uptrend intact" if above200 else " (weaker structure)"))
    if rev_w:
        rat.append(f"weekly RSI turning up from {rw:.0f}")
    elif rw < OVERSOLD:
        rat.append(f"weekly RSI {rw:.0f} (oversold)")
    if warming:
        rat.append(f"IV warming (n={iv_n})")
    else:
        rat.append(f"IV rank {iv_rank:.0f} · {'rich' if iv_rank >= QUALIFY_IVR else 'thin'}")

    # Next-session planning (all off-hours-stable — computed off the close).
    exp_move_pct = round(iv_val / TRADING_DAYS_SQRT, 2) if iv_val > 0 else 0.0   # 1-day σ from IV
    exp_move_usd = round(c * exp_move_pct / 100, 2)
    cushion = round((c - strike) / c * 100, 1) if c > 0 else 0.0
    floor_dist = round((c - s200) / c * 100, 1) if (s200 and c > 0) else 0.0

    return PremiumCandidate(
        symbol=symbol, theme=theme, price=round(c, 2),
        iv=round(iv_val, 2), iv_rank=round(iv_rank, 1), iv_pct=round(iv_pct, 1),
        iv_n=iv_n, iv_warming=warming, rsi_d=round(rd, 1), rsi_w=round(rw, 1),
        above_200=above200, above_50=above50, above_20=above20, reclaim=reclaim,
        score=score, tier=tier, qualifies=qualifies, side="put",
        strike=strike, dte=DTE, rationale=rat,
        exp_move_pct=exp_move_pct, exp_move_usd=exp_move_usd, strike_cushion_pct=cushion,
        sma20=round(s20, 2) if s20 else 0.0, sma50=round(s50, 2) if s50 else 0.0,
        sma200=round(s200, 2) if s200 else 0.0, floor_dist_pct=floor_dist,
    )


# Tier ordering for a stable sort (low risk first, then by score desc).
TIER_ORDER = {"low": 0, "med": 1, "high": 2}


def rank(cands: list[PremiumCandidate]) -> list[PremiumCandidate]:
    """Qualifying candidates first, then by tier (low→high), then score desc."""
    return sorted(cands, key=lambda k: (0 if k.qualifies else 1, TIER_ORDER[k.tier], -k.score))
