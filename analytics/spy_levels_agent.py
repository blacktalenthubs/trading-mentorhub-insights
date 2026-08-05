"""Hourly SPY Levels Agent — reads SPY's MA/EMA stack + the 4H levels and narrates where
SPY is sitting RELATIVE to each (which are support, which are resistance, above/below).

An AI heartbeat for market context during the session: not an event (like the regime-shift
narrator), a scheduled hourly read. The data (price, EMAs, SMAs, the last two 4H candles' H/L,
PDH/PDL) is computed upstream and passed in as a dict; this module just narrates it.
"""
from __future__ import annotations


# levels dict shape (all optional; missing keys are skipped):
#   price, ema8, ema20, ema50, ema100, ema200, sma50, sma100, sma200,
#   h4_1_high, h4_1_low, h4_2_high, h4_2_low, pdh, pdl,
#   pwh, pwl (prior week), pmh, pml (prior month), pqh, pql (prior quarter), session_time
def _col(df, name):
    """Case-insensitive column accessor (Alpaca lowercases, yfinance capitalizes)."""
    for c in (name, name.capitalize(), name.upper(), name.lower()):
        if c in df.columns:
            return df[c]
    return None


def compute_levels(symbol: str, is_crypto: bool = False) -> dict | None:
    """Gather SPY/BTC price + EMA/SMA stack (daily) + last-two 4H H/L + PDH/PDL.

    Daily MAs use the same Alpaca daily path the regime engine uses (yfinance fallback); the 4H
    levels come from the intraday feed (works 24/7 for crypto). Any piece that fails is simply
    omitted from the dict — the narrator skips missing levels.
    """
    from analytics.intraday_data import _fetch_alpaca_bars, fetch_intraday, fetch_intraday_crypto
    lv: dict = {}
    # ── daily bars → MA stack + PDH/PDL ────────────────────────────────────────
    daily = None
    try:
        daily = _fetch_alpaca_bars(symbol, interval="1d", hours_back=24 * 370)
    except Exception:
        daily = None
    if daily is None or len(daily) < 10:
        try:
            daily = fetch_intraday(symbol, period="1y", interval="1d")
        except Exception:
            daily = None
    if daily is not None and len(daily) >= 2:
        c, h, l = _col(daily, "close"), _col(daily, "high"), _col(daily, "low")
        if c is not None:
            lv["price"] = float(c.iloc[-1])
            for span, k in [(8, "ema8"), (20, "ema20"), (50, "ema50"), (100, "ema100"), (200, "ema200")]:
                if len(c) >= span:
                    lv[k] = float(c.ewm(span=span, adjust=False).mean().iloc[-1])
            for win, k in [(50, "sma50"), (100, "sma100"), (200, "sma200")]:
                if len(c) >= win:
                    lv[k] = float(c.rolling(win).mean().iloc[-1])
        if h is not None and l is not None and len(daily) >= 2:
            lv["pdh"], lv["pdl"] = float(h.iloc[-2]), float(l.iloc[-2])
        # prior WEEK / MONTH / QUARTER high & low (the last COMPLETED period → iloc[-2], since
        # iloc[-1] is the current developing one). Matches the pine's PWH/PWL/PMH/PML/PQH/PQL.
        if h is not None and l is not None and len(daily) >= 40:
            try:
                import pandas as _pd
                _df = _pd.DataFrame({"h": list(h.values), "l": list(l.values)}, index=_pd.DatetimeIndex(daily.index))
                for _rule, _hk, _lk in (("W", "pwh", "pwl"), ("M", "pmh", "pml"), ("Q", "pqh", "pql")):
                    _agg = _df.resample(_rule).agg({"h": "max", "l": "min"}).dropna()
                    if len(_agg) >= 2:
                        lv[_hk] = float(_agg["h"].iloc[-2])
                        lv[_lk] = float(_agg["l"].iloc[-2])
            except Exception:
                pass
    # ── intraday → last two COMPLETED 4H candles' H/L ──────────────────────────
    intr = None
    try:
        intr = fetch_intraday_crypto(symbol, interval="1h") if is_crypto else _fetch_alpaca_bars(symbol, interval="1h", hours_back=24 * 12)
    except Exception:
        intr = None
    if intr is not None and len(intr) >= 8:
        hi, lo, cl = _col(intr, "high"), _col(intr, "low"), _col(intr, "close")
        if hi is not None and lo is not None:
            try:
                agg = intr.assign(_h=hi.values, _l=lo.values).resample("4h").agg({"_h": "max", "_l": "min"}).dropna()
                if len(agg) >= 3:
                    lv["h4_1_high"], lv["h4_1_low"] = float(agg["_h"].iloc[-2]), float(agg["_l"].iloc[-2])
                    lv["h4_2_high"], lv["h4_2_low"] = float(agg["_h"].iloc[-3]), float(agg["_l"].iloc[-3])
            except Exception:
                pass
        if lv.get("price") is None and cl is not None:
            lv["price"] = float(cl.iloc[-1])
    return lv if lv.get("price") is not None else None


def _resolve_api_key() -> str:
    from alert_config import ANTHROPIC_API_KEY, ANTHROPIC_ENABLED
    if not ANTHROPIC_ENABLED:
        return ""
    if ANTHROPIC_API_KEY:
        return ANTHROPIC_API_KEY
    try:
        from db import get_db
        with get_db() as conn:
            row = conn.execute(
                "SELECT anthropic_api_key FROM user_notification_prefs "
                "WHERE anthropic_api_key != '' LIMIT 1"
            ).fetchone()
            return row["anthropic_api_key"] if row else ""
    except Exception:
        return ""


def _fmt(v) -> str:
    return "—" if v is None else f"{v:.2f}"


def _levels_block(lv: dict) -> str:
    """A compact, ORDERED (high→low) list of the levels with SPY's side marked, for the prompt."""
    price = lv.get("price")
    items = [
        ("8 EMA", lv.get("ema8")), ("20 EMA", lv.get("ema20")), ("50 EMA", lv.get("ema50")),
        ("100 EMA", lv.get("ema100")), ("200 EMA", lv.get("ema200")),
        ("50 SMA", lv.get("sma50")), ("100 SMA", lv.get("sma100")), ("200 SMA", lv.get("sma200")),
        ("4H-1 high", lv.get("h4_1_high")), ("4H-1 low", lv.get("h4_1_low")),
        ("4H-2 high", lv.get("h4_2_high")), ("4H-2 low", lv.get("h4_2_low")),
        ("PDH", lv.get("pdh")), ("PDL", lv.get("pdl")),
        ("PWH", lv.get("pwh")), ("PWL", lv.get("pwl")),
        ("PMH", lv.get("pmh")), ("PML", lv.get("pml")),
        ("PQH", lv.get("pqh")), ("PQL", lv.get("pql")),
    ]
    rows = []
    for name, val in items:
        if val is None:
            continue
        side = "" if price is None else (" (support, below price)" if val < price else " (resistance, above price)")
        rows.append(f"  {name}: {val:.2f}{side}")
    return "\n".join(rows)


def _named_levels(lv: dict) -> list:
    return [
        ("8 EMA", lv.get("ema8")), ("20 EMA", lv.get("ema20")), ("50 EMA", lv.get("ema50")),
        ("100 EMA", lv.get("ema100")), ("200 EMA", lv.get("ema200")),
        ("50 SMA", lv.get("sma50")), ("100 SMA", lv.get("sma100")), ("200 SMA", lv.get("sma200")),
        ("4H-1 high", lv.get("h4_1_high")), ("4H-1 low", lv.get("h4_1_low")),
        ("4H-2 high", lv.get("h4_2_high")), ("4H-2 low", lv.get("h4_2_low")),
        ("PDH", lv.get("pdh")), ("PDL", lv.get("pdl")),
        ("PWH", lv.get("pwh")), ("PWL", lv.get("pwl")),
        ("PMH", lv.get("pmh")), ("PML", lv.get("pml")),
        ("PQH", lv.get("pqh")), ("PQL", lv.get("pql")),
    ]


def _bracket(lv: dict):
    price = lv.get("price")
    if price is None:
        return None, None
    belows = [(n, v) for n, v in _named_levels(lv) if v is not None and v < price]
    aboves = [(n, v) for n, v in _named_levels(lv) if v is not None and v > price]
    sup = max(belows, key=lambda x: x[1], default=None)
    res = min(aboves, key=lambda x: x[1], default=None)
    return sup, res


def build_prompt(lv: dict, symbol: str = "SPY") -> str:
    price = lv.get("price")
    t = lv.get("session_time", "")
    sup, res = _bracket(lv)
    sup_s = f"{sup[1]:.2f} ({sup[0]})" if sup else "none below price"
    res_s = f"{res[1]:.2f} ({res[0]})" if res else "blue sky - nothing above price"
    return (
        f"{symbol} is at ${_fmt(price)}{(' at ' + t) if t else ''}.\n"
        f"Structural levels, each marked support (BELOW price) or resistance (ABOVE price):\n"
        f"{_levels_block(lv)}\n\n"
        f"NEAREST SUPPORT (below price): {sup_s}.  NEAREST RESISTANCE (above price): {res_s}.\n\n"
        "Reply in EXACTLY 3 short lines - no preamble, no bold:\n"
        "Line 1 - bias in <=8 words. It MUST agree with the levels: price is ABOVE every support and BELOW "
        "every resistance. Do NOT say price is above a resistance or below a support.\n"
        "Line 2 - Support <price> (<name>) - Resistance <price> (<name>): use the NEAREST SUPPORT and NEAREST "
        "RESISTANCE given above, VERBATIM. If nothing is above, write Resistance: blue sky.\n"
        "Line 3 - Action: ONE concrete trigger: long on a BREAK/RECLAIM ABOVE the resistance (price is below "
        "it), stop BELOW the support. In blue sky, hold/trail - no invented target.\n"
        "HARD RULES: (1) every price MUST be one of the levels above. (2) A RESISTANCE sits ABOVE price so the "
        "only long trigger is a BREAK/RECLAIM ABOVE it; NEVER say price is already above it. A SUPPORT sits "
        "BELOW price so the action is hold-above / stop-below it. Never contradict these."
    )


SYSTEM = (
    "You are a terse trade-desk reading a symbol against its KEY STRUCTURE — the prior day/week/month/quarter "
    "highs & lows, the last two 4H candle H/L, and the MA stack. Output is a 3-line action card, not prose: "
    "bias, the bracketing support/resistance, ONE concrete action trigger. EVERY price you cite MUST be one of "
    "the named levels you were given — NEVER invent a number, and always name the level (PDL, PWH, 50 SMA, "
    "4H-1 low, …) next to its price. A RESISTANCE sits ABOVE price and a SUPPORT BELOW it - NEVER contradict that (never say price is above a "
    "resistance, or break above a support). No hedging, no fluff. Probabilistic, never a guarantee."
)


def narrate(lv: dict, symbol: str = "SPY", model: str | None = None) -> str:
    """AI read of `symbol` vs its levels. Falls back to a structured template if the API is unavailable."""
    key = _resolve_api_key()
    if not key:
        return fallback(lv, symbol)
    try:
        from alert_config import CLAUDE_MODEL
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=model or CLAUDE_MODEL,
            max_tokens=130,
            system=SYSTEM,
            messages=[{"role": "user", "content": build_prompt(lv, symbol)}],
        )
        txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return txt or fallback(lv, symbol)
    except Exception:
        return fallback(lv, symbol)


def fallback(lv: dict, symbol: str = "SPY") -> str:
    """Deterministic structured read if the AI is unavailable — NAMED levels only, still useful."""
    price = lv.get("price")
    if price is None:
        return f"{symbol} levels unavailable."
    named = [
        ("8 EMA", lv.get("ema8")), ("20 EMA", lv.get("ema20")), ("50 EMA", lv.get("ema50")),
        ("100 EMA", lv.get("ema100")), ("200 EMA", lv.get("ema200")),
        ("50 SMA", lv.get("sma50")), ("100 SMA", lv.get("sma100")), ("200 SMA", lv.get("sma200")),
        ("4H-1 high", lv.get("h4_1_high")), ("4H-1 low", lv.get("h4_1_low")),
        ("4H-2 high", lv.get("h4_2_high")), ("4H-2 low", lv.get("h4_2_low")),
        ("PDH", lv.get("pdh")), ("PDL", lv.get("pdl")),
        ("PWH", lv.get("pwh")), ("PWL", lv.get("pwl")),
        ("PMH", lv.get("pmh")), ("PML", lv.get("pml")),
        ("PQH", lv.get("pqh")), ("PQL", lv.get("pql")),
    ]
    belows = [(n, v) for n, v in named if v is not None and v < price]
    aboves = [(n, v) for n, v in named if v is not None and v > price]
    sup = max(belows, key=lambda x: x[1], default=None)   # nearest below
    res = min(aboves, key=lambda x: x[1], default=None)   # nearest above
    emas = [lv.get(k) for k in ("ema8", "ema20", "ema50", "ema100", "ema200")]
    above_ct = sum(1 for v in emas if v is not None and price > v)
    bias = "bullish stack" if above_ct >= 4 else "bearish — no long" if above_ct <= 1 else "mixed / chop"
    l1 = f"{symbol} ${price:.2f} — {bias}"
    _sup = f"Support {sup[1]:.2f} ({sup[0]})" if sup else "Support: none below"
    _res = f"Resistance {res[1]:.2f} ({res[0]})" if res else "Resistance: blue sky"
    l2 = f"{_sup} · {_res}"
    if sup and res:
        l3 = f"Action: long on reclaim of {res[0]} {res[1]:.2f}; short on loss of {sup[0]} {sup[1]:.2f}"
    elif sup:
        l3 = f"Action: hold above {sup[0]} {sup[1]:.2f} — blue sky above, trail"
    elif res:
        l3 = f"Action: stand aside below {res[0]} {res[1]:.2f}"
    else:
        l3 = "Action: stand aside — no level bracket"
    return "\n".join((l1, l2, l3))
