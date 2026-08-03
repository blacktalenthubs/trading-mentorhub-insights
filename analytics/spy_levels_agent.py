"""Hourly SPY Levels Agent — reads SPY's MA/EMA stack + the 4H levels and narrates where
SPY is sitting RELATIVE to each (which are support, which are resistance, above/below).

An AI heartbeat for market context during the session: not an event (like the regime-shift
narrator), a scheduled hourly read. The data (price, EMAs, SMAs, the last two 4H candles' H/L,
PDH/PDL) is computed upstream and passed in as a dict; this module just narrates it.
"""
from __future__ import annotations


# levels dict shape (all optional; missing keys are skipped):
#   price, ema8, ema20, ema50, ema100, ema200, sma50, sma100, sma200,
#   h4_1_high, h4_1_low, h4_2_high, h4_2_low, pdh, pdl, session_time
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
    ]
    rows = []
    for name, val in items:
        if val is None:
            continue
        side = "" if price is None else (" (support, below price)" if val < price else " (resistance, above price)")
        rows.append(f"  {name}: {val:.2f}{side}")
    return "\n".join(rows)


def build_prompt(lv: dict, symbol: str = "SPY") -> str:
    price = lv.get("price")
    t = lv.get("session_time", "")
    return (
        f"{symbol} is at ${_fmt(price)}{(' at ' + t) if t else ''}.\n"
        f"Its moving averages and 4H levels, each marked as support (below price) or resistance (above):\n"
        f"{_levels_block(lv)}\n\n"
        "Reply in EXACTLY 3 short lines — no preamble, no bold, no extra words:\n"
        "Line 1 — bias in ≤7 words (e.g. 'Above 8/20/50 EMA — bullish stack' or 'Below all MAs — no long').\n"
        "Line 2 — 'Support <price> (<name>) · Resistance <price> (<name>)' using the NEAREST below/above.\n"
        "Line 3 — 'Action:' then ONE concrete trigger: long on a reclaim of the resistance, short on a loss "
        "of the support, or stand aside if it's chop in the middle. Name the exact level to act on."
    )


SYSTEM = (
    "You are a terse trade-desk. Output is a 3-line action card, not prose. Every line earns its place: "
    "bias, the bracketing support/resistance, and ONE concrete action trigger. No hedging, no fluff, "
    "no restating the inputs. Probabilistic, never a guarantee."
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
    """Deterministic structured read if the AI is unavailable — still useful."""
    price = lv.get("price")
    if price is None:
        return f"{symbol} levels unavailable."
    emas = [("8 EMA", lv.get("ema8")), ("20 EMA", lv.get("ema20")), ("50 EMA", lv.get("ema50")),
            ("100 EMA", lv.get("ema100")), ("200 EMA", lv.get("ema200"))]
    above = [n for n, v in emas if v is not None and price > v]
    below = [n for n, v in emas if v is not None and price < v]
    sup = max((v for _n, v in [("4H-1 low", lv.get("h4_1_low")), ("4H-2 low", lv.get("h4_2_low")),
              ("PDL", lv.get("pdl"))] + emas if v is not None and v < price), default=None)
    res = min((v for _n, v in [("4H-1 high", lv.get("h4_1_high")), ("4H-2 high", lv.get("h4_2_high")),
              ("PDH", lv.get("pdh"))] + emas if v is not None and v > price), default=None)
    bias = "bullish stack" if len(above) >= 4 else "bearish — no long" if len(below) >= 4 else "mixed / chop"
    l1 = f"{symbol} ${price:.2f} — {bias}"
    l2 = f"Support {sup:.2f} · Resistance {res:.2f}" if (sup and res) else (f"Support {sup:.2f}" if sup else (f"Resistance {res:.2f}" if res else ""))
    l3 = f"Action: long on reclaim of {res:.2f}, short on loss of {sup:.2f}" if (sup and res) else ""
    return "\n".join(x for x in (l1, l2, l3) if x)
