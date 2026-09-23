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
# Suggested short-put distance OTM by tier — safer tier sits closer, riskier further out.
OTM_BY_TIER = {"low": 0.03, "med": 0.05, "high": 0.08}
DTE = 30

# Composite weights — premium is why we're here, structure is safety, RSI is timing.
W_IV, W_TREND, W_RSI = 0.40, 0.35, 0.25

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


def _trend_score(price, s20, s50, s200, r20, r50, above20, above50, above200) -> float:
    v = 50.0
    v += 20 if above200 else -28
    if above50 and r50:
        v += 12
    elif not above50:
        v -= 8
    if above20 and r20:
        v += 8
    elif not above20:
        v -= 8
    return max(0.0, min(100.0, v))


def _rsi_score(rd, rw, rev_d, rev_w) -> float:
    v = 50.0
    # Daily timing — a reversal off oversold is the best moment to sell a put into a bottom.
    if rev_d:
        v += 22
    if OVERSOLD <= rd <= 60:
        v += 8
    if rd > OVERBOUGHT:
        v -= 18          # overbought → a pullback is exactly the put-seller's risk
    if rd < 30 and not rev_d:
        v -= 15          # deep and still falling → knife
    # Weekly regime.
    if rev_w:
        v += 10
    if rw < 30 and not rev_w:
        v -= 12
    if rw > OVERBOUGHT:
        v -= 6
    return max(0.0, min(100.0, v))


def _tier(above200, above50, r50, rd, rw, rev_d) -> str:
    # HIGH — structure is broken or price is a falling knife: premium is rich for a bad reason.
    if not above200 or (rw < 30 and not rev_d) or (rd < 30 and not rev_d):
        return "high"
    # LOW — above a rising-enough structure, RSI not stretched, weekly not oversold.
    if above200 and above50 and r50 and rd <= OVERBOUGHT and rw >= OVERSOLD:
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

    # A key MA reclaimed / bounced RIGHT NOW (open-above wick-hold) — timing bonus.
    reclaim = ""
    if (r20 and _bounce(o, l, c, s20, MA_TOL)) or (r50 and _bounce(o, l, c, s50, MA_TOL)):
        reclaim = "20/50 MA"
    elif _bounce(o, l, c, s200, MA_TOL):
        reclaim = "200 SMA"

    # IV factor.
    if iv is None:
        iv_val, iv_rank, iv_pct, iv_n = 0.0, 0.0, 0.0, 0
        warming = True
    else:
        iv_val, iv_rank, iv_pct, iv_n = iv["iv"], iv["rank"], iv["percentile"], iv["n"]
        warming = iv_n < MIN_HISTORY

    trend = _trend_score(c, s20, s50, s200, r20, r50, above20, above50, above200)
    rsi_s = _rsi_score(rd, rw, rev_d, rev_w)
    # While warming, the rank is meaningless → lean on structure + timing (neutral IV compo).
    iv_compo = 50.0 if warming else iv_rank
    score = round(W_IV * iv_compo + W_TREND * trend + W_RSI * rsi_s, 1)

    tier = _tier(above200, above50, r50, rd, rw, rev_d)
    qualifies = warming or iv_rank >= QUALIFY_IVR
    otm = OTM_BY_TIER[tier]
    strike = round(c * (1 - otm), 2)

    # Human rationale — what the desk shows for "why this, why now".
    rat: list[str] = []
    if warming:
        rat.append(f"IV history warming (n={iv_n})")
    else:
        rich = "rich" if iv_rank >= QUALIFY_IVR else "thin"
        rat.append(f"IV rank {iv_rank:.0f} · {rich} (IV {iv_val:.0f}%, n={iv_n})")
    struct = "above" if above200 else "below"
    parts = []
    if above20:
        parts.append("20")
    if above50:
        parts.append("50")
    if parts and above200:
        rat.append(f"above rising {'/'.join(parts)} & 200 SMA" if (r20 or r50) else f"above {'/'.join(parts)} & 200 SMA")
    else:
        rat.append(f"{struct} 200 SMA")
    if reclaim:
        rat.append(f"reclaiming {reclaim} now")
    if rev_d:
        rat.append(f"daily RSI reversal from {rd:.0f}")
    else:
        rat.append(f"daily RSI {rd:.0f}")
    rat.append(f"weekly RSI {rw:.0f}" + (" (oversold)" if rw < OVERSOLD else ""))

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
