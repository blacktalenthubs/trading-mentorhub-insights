"""LEAP Desk scan — hunt deep-oversold entries on strong companies for long-dated calls.

The thesis (trader's own): buy a 12-24mo ITM call (a stock replacement) on a STRONG name
caught at a rare oversold — RSI under 30 daily, or the generational weekly-RSI washout, or
a tag of the 200-day. The LEAP buys time for the thesis to work while the stock wiggles.

Two things this scan enforces, because they're the failure modes of the strategy:
  1. QUALITY GATE — RSI < 30 also fires on falling knives / value traps. A stock only makes
     the desk if it passes a fundamentals gate (size, revenue growth, profitability, analyst
     consensus). Index ETFs skip the gate (inherently diversified) and are treated as elite.
  2. QUALITY-SCALED RSI — the elite names (AAPL/GOOGL) rarely reach 30; they get bought first.
     So the RSI trigger relaxes with quality: gate = 30 + bonus(0..5), i.e. up to ~35 for the
     strongest names, weekly up to ~40. Merely-strong names still need the deeper < 30 discount.

Same shape as premium_desk_scan: pull daily+weekly bars, read fundamentals + IV, score, publish
to market_reports(kind='leap_desk'). Timing/analytics only — verify the live chain before buying.

CLI: `python3 -m analytics.leap_scan [--publish]`
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import leap_universe  # noqa: E402

# Breadth proxies — indexes whose weakness vs cap-weight SPY signals a BROAD-market washout
# (the average stock is being sold, not just the index optics). An equal-weight / mid / small
# index oversold WHILE SPY holds up is the real "breadth divergence" tell.
BREADTH_VS_SPY = {"RSP": "equal-weight S&P", "MDY": "mid-caps", "IWM": "small-caps"}
BREADTH_GAP = 5.0        # index RSI must be this many points below SPY's to flag divergence

MC_FLOOR = 10e9          # $10B — big enough for deep, liquid LEAP chains
RSI_BASE_D = 30.0        # daily oversold gate for a merely-strong name
RSI_BASE_W = 35.0        # weekly oversold gate (the generational signal)
LEAP_DELTA_STRIKE = 0.80  # suggested strike ≈ 20% ITM ≈ ~0.75-0.8 delta (stock-replacement)
LEAP_DTE = 540           # ~18-month target LEAP


def _daily(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="14mo", interval="1d")
    return None if df is None or df.empty else df.dropna()


def _weekly(sym):  # pragma: no cover - network
    from analytics.market_data import fetch_ohlc
    df = fetch_ohlc(sym, period="5y", interval="1wk")
    return None if df is None or df.empty else df.dropna()


def _read_fundamentals(syms):  # pragma: no cover - DB
    """Batch-read the nightly Finnhub fundamentals from symbol_fundamentals. Returns
    {SYM: {market_cap, eps_growth_pct, pe_ratio, consensus, revenue_growth_pct,
    gross_margin_pct, net_margin_pct}} — margins/growth live in metrics_json."""
    out: dict[str, dict] = {}
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return out
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=12)
        cur = conn.cursor()
        cur.execute(
            "SELECT UPPER(symbol), market_cap, eps_growth_pct, pe_ratio, consensus, metrics_json "
            "FROM symbol_fundamentals WHERE UPPER(symbol) = ANY(%s)",
            ([s.upper() for s in syms],),
        )
        for sym, mc, epsg, pe, cons, mj in cur.fetchall():
            d = {"market_cap": mc, "eps_growth_pct": epsg, "pe_ratio": pe, "consensus": cons}
            try:
                m = json.loads(mj) if mj else {}
                d["revenue_growth_pct"] = m.get("revenue_growth_pct")
                d["gross_margin_pct"] = m.get("gross_margin_pct")
                d["net_margin_pct"] = m.get("net_margin_pct")
            except Exception:
                pass
            out[sym] = d
        cur.close(); conn.close()
    except Exception:
        pass
    return out


def _rsi_last(series):
    from analytics.support_signals import _rsi
    r = _rsi(series.astype(float))
    return float(r.iloc[-1]) if len(r) else float("nan")


def _quality(fund, is_idx):
    """(score 0-100, bonus 0-5, tier, passes_gate, warming, reasons). Index = elite, no gate."""
    if is_idx:
        return 90.0, 5, "elite", True, False, ["index — inherently diversified, no single-name risk"]
    if not fund:
        # Curated universe = trusted quality; a missing fundamentals row is "warming", not a fail.
        return 50.0, 2, "warming", True, True, ["fundamentals warming — not yet verified"]
    mc = fund.get("market_cap")
    rev = fund.get("revenue_growth_pct")
    nm = fund.get("net_margin_pct")
    gm = fund.get("gross_margin_pct")
    epsg = fund.get("eps_growth_pct")
    cons = (fund.get("consensus") or "").lower()
    reasons: list[str] = []
    # Base gate — what makes it LEAP-worthy vs a falling knife.
    big = mc is not None and mc >= MC_FLOOR
    profitable = nm is not None and nm > 0
    growing = rev is not None and rev > 0
    not_broken = "sell" not in cons  # "sell" / "strong sell" fail
    passes = big and profitable and growing and not_broken
    score = 0.0
    if mc is not None:
        score += 30 if mc >= 1e12 else 22 if mc >= 200e9 else 14 if mc >= 50e9 else 8 if mc >= MC_FLOOR else 0
    if rev is not None:
        score += 15 if rev >= 20 else 10 if rev >= 10 else 5 if rev > 0 else -10
        if rev >= 10:
            reasons.append(f"rev +{rev:.0f}%")
    if nm is not None:
        score += 15 if nm >= 20 else 10 if nm >= 10 else 5 if nm > 0 else -15
        if nm > 0:
            reasons.append(f"net margin {nm:.0f}%")
    if gm is not None:
        score += 12 if gm >= 60 else 7 if gm >= 40 else 3 if gm > 0 else 0
    if epsg is not None and epsg > 0:
        score += 8
    if cons in ("buy", "strong buy"):
        score += 10
        reasons.append("analysts buy")
    elif "sell" in cons:
        score -= 20
    score = max(0.0, min(100.0, score))
    tier = "elite" if score >= 75 else "strong" if score >= 55 else "warming" if passes else "fail"
    # RSI-gate bonus by quality tier: elite reaches ~35 (they rarely go lower), strong ~32,
    # merely-passing ~30. This is the "consider AAPL/GOOGL around 35" rule.
    bonus = 5 if tier == "elite" else 2 if tier == "strong" else 0
    if not passes:
        reasons.append("fails quality gate")
    return score, bonus, tier, passes, False, reasons


def score_leap(sym, daily, weekly, fund, iv, is_idx, spy_rsi_d=None):
    if daily is None or weekly is None or len(daily) < 30 or len(weekly) < 10:
        return None
    dc = daily["Close"].astype(float)
    price = float(dc.iloc[-1])
    rsi_d = _rsi_last(dc)
    rsi_w = _rsi_last(weekly["Close"])
    sma200 = float(dc.rolling(200).mean().iloc[-1]) if len(dc) >= 200 else float("nan")
    sma50 = float(dc.rolling(50).mean().iloc[-1]) if len(dc) >= 50 else float("nan")
    dist_200 = (price - sma200) / sma200 * 100.0 if not math.isnan(sma200) and sma200 > 0 else float("nan")
    at_200 = not math.isnan(dist_200) and dist_200 <= 1.0   # at or below the 200 (within 1%)

    q_score, bonus, q_tier, passes, warming, q_reasons = _quality(fund, is_idx)
    if not passes:
        return None  # falling knife / value trap — never a LEAP candidate

    rsi_gate_d = RSI_BASE_D + bonus
    rsi_gate_w = min(RSI_BASE_W + bonus, 42.0)
    deep_d = not math.isnan(rsi_d) and rsi_d <= rsi_gate_d
    deep_w = not math.isnan(rsi_w) and rsi_w <= rsi_gate_w
    near_200 = at_200 and not math.isnan(rsi_d) and rsi_d < 45.0
    qualifies = deep_d or deep_w or near_200

    # Opportunity tier — how good the shot is.
    if deep_w and at_200:
        tier = "prime"
    elif qualifies:
        tier = "strong"
    elif passes and ((not math.isnan(rsi_d) and rsi_d <= rsi_gate_d + 7) or (not math.isnan(dist_200) and dist_200 <= 4.0)):
        tier = "watch"
    else:
        return None  # nothing near — off the desk

    # Rationale
    rat: list[str] = []
    if deep_w:
        rat.append(f"weekly RSI {rsi_w:.0f} — generational oversold")
    if deep_d:
        rat.append(f"daily RSI {rsi_d:.0f} ≤ {rsi_gate_d:.0f}")
    if at_200:
        rat.append("at/below the 200-day")
    elif not math.isnan(dist_200) and dist_200 <= 4.0:
        rat.append(f"{dist_200:.1f}% above the 200-day")
    rat += q_reasons
    # Breadth divergence — a breadth index (RSP/MDY/IWM) oversold vs cap-weight SPY. The real
    # tell: the average stock got flushed while the mega-caps masked it. Leads the rationale.
    breadth = (is_idx and sym in BREADTH_VS_SPY and spy_rsi_d is not None
               and not math.isnan(rsi_d) and rsi_d < 50.0 and rsi_d <= spy_rsi_d - BREADTH_GAP)
    if breadth:
        rat.insert(0, f"breadth washout — {BREADTH_VS_SPY[sym]} oversold (RSI {rsi_d:.0f}) vs cap-weight SPY {spy_rsi_d:.0f}")
    if tier == "watch" and not rat:
        rat.append("approaching the entry zone")

    # IV lens — for BUYING a LEAP, cheaper (low IV rank) is better; flag rich.
    ivr = iv.get("iv_rank") if iv else None
    iv_warming = iv is None or (iv or {}).get("n", 0) < 20
    iv_note = "" if ivr is None else "cheap LEAP" if ivr <= 30 else "rich — pricey LEAP" if ivr >= 70 else "fair"

    # Two strike ideas, two risk appetites (both snapped to real listed strikes):
    #   ITM (~0.8Δ)  — stock replacement: high probability, low theta, muted upside.
    #   TARGET play  — a strike AT the nearest OVERHEAD RESISTANCE the bounce aims for (the way the
    #                  trader sizes it: entered GOOGL at the 200-SMA, targeted 365 = the resistance
    #                  above the MA cluster). We take the closest of {50/100/200-day SMA, 60-day
    #                  high} that sits at least 3% above price — so an MA hugging price is skipped
    #                  (no clear air) and we aim for the next real level up. Fallback ~10% OTM.
    sma100 = float(dc.rolling(100).mean().iloc[-1]) if len(dc) >= 100 else float("nan")
    hi60 = float(dc.iloc[-60:].max()) if len(dc) >= 20 else float("nan")
    _cand = [(v, nm) for v, nm in ((sma50, "50-day"), (sma100, "100-day"), (sma200, "200-day"),
                                   (hi60, "60-day high")) if not math.isnan(v) and v > price * 1.03]
    _cand.sort()
    strike_itm = _round_strike(price * LEAP_DELTA_STRIKE)
    if _cand:
        strike_target, target_basis = _round_strike(_cand[0][0]), _cand[0][1]
    else:
        strike_target, target_basis = _round_strike(price * 1.10), "~10% OTM"
    expiry = (_dt.date.today() + _dt.timedelta(days=LEAP_DTE)).isoformat()

    return {
        "sym": sym, "name": sym, "kind": "index" if is_idx else "stock", "price": round(price, 2),
        "tier": tier, "qualifies": qualifies,
        "rsi_d": None if math.isnan(rsi_d) else round(rsi_d, 1),
        "rsi_w": None if math.isnan(rsi_w) else round(rsi_w, 1),
        "sma200": None if math.isnan(sma200) else round(sma200, 2),
        "sma50": None if math.isnan(sma50) else round(sma50, 2),
        "dist_200_pct": None if math.isnan(dist_200) else round(dist_200, 1),
        "at_200": at_200,
        "quality_score": round(q_score, 0), "quality_tier": q_tier, "quality_warming": warming,
        "grade": _grade(q_score),
        "market_cap": (fund or {}).get("market_cap"),
        "rev_growth": (fund or {}).get("revenue_growth_pct"),
        "net_margin": (fund or {}).get("net_margin_pct"),
        "gross_margin": (fund or {}).get("gross_margin_pct"),
        "eps_growth": (fund or {}).get("eps_growth_pct"),
        "consensus": (fund or {}).get("consensus"),
        "iv_rank": ivr, "iv_warming": iv_warming, "iv_note": iv_note,
        "strike": strike_itm, "strike_itm": strike_itm, "strike_target": strike_target,
        "target_basis": target_basis, "dte": LEAP_DTE, "expiry": expiry,
        "breadth": breadth, "rationale": rat,
    }


def _round_strike(x):
    """Snap to a realistic listed-option strike increment ($2.5 / $5 / $10 by price)."""
    if x <= 0:
        return round(x, 2)
    step = 2.5 if x < 25 else 5.0 if x < 200 else 10.0
    return round(round(x / step) * step, 2)


def _grade(score):
    """Fundamentals letter grade — A = top quality, D = weakest that still passed the gate.
    Same idea as the premium desk's ranking, so LEAP names sort/analyze the same way."""
    return "A" if score >= 78 else "B" if score >= 62 else "C" if score >= 50 else "D"


_TIER_RANK = {"prime": 0, "strong": 1, "watch": 2}


def scan(symbols=None):  # pragma: no cover - network
    from analytics.iv_snapshot import iv_rank
    syms = [s.upper() for s in (symbols or leap_universe.UNIVERSE)]
    funds = _read_fundamentals(syms)
    # Cap-weight SPY RSI — the breadth benchmark the equal-weight/broad indexes are judged against.
    spy_rsi_d = None
    try:
        _sd = _daily("SPY")
        if _sd is not None and len(_sd) > 20:
            spy_rsi_d = _rsi_last(_sd["Close"])
    except Exception:
        pass
    rows = []
    for sym in syms:
        try:
            try:
                iv = iv_rank(sym)
            except Exception:
                iv = None
            c = score_leap(sym, _daily(sym), _weekly(sym), funds.get(sym), iv, leap_universe.is_index(sym), spy_rsi_d)
            if c:
                rows.append(c)
        except Exception:
            pass
    rows.sort(key=lambda r: (_TIER_RANK.get(r["tier"], 9), -(r["quality_score"] or 0), r["rsi_d"] if r["rsi_d"] is not None else 99))
    return {"rows": rows, "scanned": len(syms),
            "tiers": {t: sum(1 for r in rows if r["tier"] == t) for t in ("prime", "strong", "watch")}}


def publish(rep, session_date):  # pragma: no cover - DB
    import psycopg2
    conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=15)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
        kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
    cur.execute(
        "INSERT INTO market_reports (kind, session_date, body) VALUES ('leap_desk', %s, %s) "
        "ON CONFLICT (kind, session_date) DO UPDATE SET body = EXCLUDED.body, created_at = NOW()",
        (session_date, json.dumps(rep)),
    )
    conn.commit(); cur.close(); conn.close()


def _print(rep):
    t = rep["tiers"]
    print(f"\n=== LEAP DESK === scanned {rep['scanned']} · "
          f"{t['prime']} prime · {t['strong']} strong · {t['watch']} watch\n")
    for r in rep["rows"]:
        gate = "✓" if r["qualifies"] else "·"
        rd = f"{r['rsi_d']:>4.0f}" if r["rsi_d"] is not None else "  · "
        rw = f"{r['rsi_w']:>4.0f}" if r["rsi_w"] is not None else "  · "
        print(f"  {gate} [{r['tier']:>6}] {r['sym']:<6} {r['kind']:<5} ${r['price']:>8.2f}  "
              f"RSI d{rd}/w{rw}  Q{r['quality_score']:>3.0f}  "
              f"buy ~{r['strike']:>8.2f} call {r['expiry']}  — {' · '.join(r['rationale'])}")


def main():  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--symbols", default="")
    a = ap.parse_args()
    syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()] or None
    rep = scan(syms)
    _print(rep)
    if a.publish:
        publish(rep, _dt.date.today().isoformat())
        print("published: leap_desk", _dt.date.today().isoformat(), file=sys.stderr)


if __name__ == "__main__":
    main()
