"""Hourly Levels Agent — reads a symbol against its STRUCTURAL stack (MA/EMA + prior
day/week/month/quarter H/L + the 30-week MA) and narrates where price sits relative to each
(which are support, which resistance) plus the 1h trend (buying/selling).

An AI heartbeat for market context during the session: a scheduled hourly read. Output is a
SOLID deterministic 3-line card — bias (+1h trend), bracketing support/resistance, ONE action —
with only the short bias phrase written by the model. Data is computed upstream and passed in.
"""
from __future__ import annotations


# levels dict shape (all optional; missing keys are skipped):
#   price, ema8, ema20, ema50, ema100, ema200, sma50, sma100, sma200,
#   w30 (30-week MA), h1_trend ("buying ↑" / "selling ↓" / "mixed →"), pdh, pdl,
#   pwh, pwl (prior week), pmh, pml (prior month), pqh, pql (prior quarter), session_time
def _col(df, name):
    """Case-insensitive column accessor (Alpaca lowercases, yfinance capitalizes)."""
    for c in (name, name.capitalize(), name.upper(), name.lower()):
        if c in df.columns:
            return df[c]
    return None


def compute_levels(symbol: str, is_crypto: bool = False) -> dict | None:
    """Gather price + EMA/SMA stack (daily) + 30-week MA + PDH/PDL/PWH/PWL/PMH/PML/PQH/PQL + 1h trend.

    Daily MAs use the same Alpaca daily path the regime engine uses (yfinance fallback); the 1h
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
                # 30-week MA (Weinstein Stage line) — from weekly closes
                if c is not None:
                    _wc = _pd.Series(list(c.values), index=_pd.DatetimeIndex(daily.index)).resample("W").last().dropna()
                    if len(_wc) >= 30:
                        lv["w30"] = float(_wc.rolling(30).mean().iloc[-1])
            except Exception:
                pass
    # ── intraday 1h → HOURLY TREND (buying/selling) ─────────────────────────────
    intr = None
    try:
        intr = fetch_intraday_crypto(symbol, interval="1h") if is_crypto else _fetch_alpaca_bars(symbol, interval="1h", hours_back=24 * 12)
    except Exception:
        intr = None
    if intr is not None and len(intr) >= 8:
        cl = _col(intr, "close")
        if cl is not None:
            if lv.get("price") is None:
                lv["price"] = float(cl.iloc[-1])
            # HOURLY TREND — 1h 8/20 EMA + slope → buying / selling / mixed (user 2026-08-05)
            try:
                _e8 = cl.ewm(span=8, adjust=False).mean()
                _e20 = cl.ewm(span=20, adjust=False).mean()
                _up = float(_e8.iloc[-1]) > float(_e20.iloc[-1])
                _rising = float(_e8.iloc[-1]) > float(_e8.iloc[-4]) if len(_e8) >= 4 else _up
                lv["h1_trend"] = "buying ↑" if (_up and _rising) else "selling ↓" if (not _up and not _rising) else "mixed →"
            except Exception:
                pass
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
        ("30W MA", lv.get("w30")),
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
        ("30W MA", lv.get("w30")),
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
    tr = lv.get("h1_trend", "n/a")
    sup, res = _bracket(lv)
    sup_s = f"{sup[1]:.2f} ({sup[0]})" if sup else "none below price"
    res_s = f"{res[1]:.2f} ({res[0]})" if res else "blue sky - nothing above price"
    return (
        f"{symbol} is at ${_fmt(price)}{(' at ' + t) if t else ''}. 1h trend: {tr}.\n"
        f"Structural levels, each marked support (BELOW price) or resistance (ABOVE price):\n"
        f"{_levels_block(lv)}\n\n"
        f"Nearest support: {sup_s}.  Nearest resistance: {res_s}.\n\n"
        "Reply with ONLY a bias phrase of <=8 words that AGREES with the levels and the 1h trend "
        "(price is ABOVE every support and BELOW every resistance). Name the key level(s) it hugs. "
        "No prices, no prose, no bold. Example: 'above PDH + all EMAs, 1h buying'."
    )


SYSTEM = (
    "You are a terse trade desk. Given a symbol's price versus its MA stack and its prior day/week/month/"
    "quarter highs & lows and the 30-week MA, reply with ONLY a BIAS phrase of <=8 words — no prices, no "
    "punctuation-heavy prose. Examples: 'above PDH + all EMAs, bullish', 'below PWL + 50 SMA, weak', "
    "'coiled between 50 & 100 SMA, mixed'. Just the bias, nothing else."
)


def _det_bias(lv: dict) -> str:
    price = lv.get("price")
    emas = [lv.get(k) for k in ("ema8", "ema20", "ema50", "ema100", "ema200")]
    above = sum(1 for v in emas if v is not None and price is not None and price > v)
    return "above the stack, bullish" if above >= 4 else "below the stack, weak" if above <= 1 else "mid-stack, mixed"


def _card(lv: dict, symbol: str, bias: str) -> str:
    """Deterministic 3-line card — SOLID formatting, always consistent. S/R + action from _bracket."""
    price = lv.get("price")
    sup, res = _bracket(lv)
    _s = f"{sup[1]:,.2f} {sup[0]}" if sup else "none"
    _r = f"{res[1]:,.2f} {res[0]}" if res else "blue sky"
    _tr = lv.get("h1_trend")
    l1 = f"{symbol} ${price:,.2f} — {bias}" + (f"  · 1h {_tr}" if _tr else "")
    l2 = f"S {_s}   ·   R {_r}"
    if sup and res:
        l3 = f"▶ Long on reclaim > {res[0]} {res[1]:,.2f} · stop < {sup[0]} {sup[1]:,.2f}"
    elif sup:
        l3 = f"▶ Hold above {sup[0]} {sup[1]:,.2f} · blue sky, trail"
    elif res:
        l3 = f"▶ Wait for a reclaim > {res[0]} {res[1]:,.2f}"
    else:
        l3 = "▶ No clean bracket — stand aside"
    return "\n".join((l1, l2, l3))


def narrate(lv: dict, symbol: str = "SPY", model: str | None = None) -> str:
    """SOLID deterministic card (S/R + action) with a short AI-written bias phrase (falls back to a
    deterministic bias if the API is down)."""
    if lv.get("price") is None:
        return f"{symbol} levels unavailable."
    bias = _det_bias(lv)
    key = _resolve_api_key()
    if key:
        try:
            from alert_config import CLAUDE_MODEL
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            resp = client.messages.create(
                model=model or CLAUDE_MODEL, max_tokens=24, system=SYSTEM,
                messages=[{"role": "user", "content": build_prompt(lv, symbol)}],
            )
            txt = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
            if txt:
                bias = txt.split("\n")[0].strip(' .·-')[:56]
        except Exception:
            pass
    return _card(lv, symbol, bias)


def fallback(lv: dict, symbol: str = "SPY") -> str:
    if lv.get("price") is None:
        return f"{symbol} levels unavailable."
    return _card(lv, symbol, _det_bias(lv))
