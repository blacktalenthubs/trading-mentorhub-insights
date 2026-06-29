#!/usr/bin/env python3
"""Morning "Monthly Breakout Watch" — the daily focus picks, built on ONLY our two
validated monthly breakout patterns. No IBD, no RS gate, no borrowed styles.

  1. MoBO  — the LOCKED flat multi-month box ceiling (Darvas base) breaking. Highest
             conviction; the MU/SNDK "next-big-mover-off-a-tight-base" pattern.
  2. RC-H  — monthly RECLAIM-HIGH: a break of a prior MONTHLY swing high that capped
             price for months (the high-side complement to RC reclaim-low). Catches the
             stair-step / no-flat-base leaders (TVTX off ~31, etc.) that MoBO can't see.

The job is to surface watchlist names sitting AT one of these breakouts — coiling just
under the level or just clearing it — NOT names already extended past it. The LEVEL is
monthly (locked); the TRIGGER/zone is checked on the DAILY price, never a monthly close
(by then price has run far off the level — IBD doesn't wait for one and neither do we).

Runs locally (yfinance works off-cloud). Prints a markdown report + JSON the morning
agent pushes to all users (market_reports kind=morning_focus).

    DATABASE_URL=postgresql://... python3 analytics/morning_leaders.py --top 3

Gate = a breakout pattern (MoBO or RC-H) with the DAILY price IN the zone (within ±zone%
of the level) AND Stage-2 (above the 200-DMA). Ranked by conviction (MoBO > RC-H), a
volume surge, base tightness, and proximity to the level. SPY 8/21 health modulates SIZE.
"""
from __future__ import annotations
import argparse, json, math, os, sys
from datetime import datetime


def _watchlist(dsn):
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE symbol IS NOT NULL AND symbol<>''")
    syms = sorted(r[0] for r in cur.fetchall())
    cur.close(); conn.close()
    return syms


def _monthly_box(mh, ml, mc, N=4, min_flat=3):
    """MoBO — the locked MONTHLY box ceiling price is CURRENTLY coiling under (never closed
    above it). Lock-step with the pine f_box: the box arms on an established FLAT ceiling
    while price stays inside it, and RETIRES on any close ABOVE the ceiling (breakout /
    clear) or BELOW the base low (failed base). So it returns a level only for a fresh
    pre-breakout coil. A name that already closed above the ceiling and fell back (a failed
    breakout, e.g. AAPL closing $312 over a $288.62 box then collapsing to $283) returns
    None — the stale ceiling no longer masquerades as a buy point."""
    n = len(mc)
    if n < N + min_flat + 2:
        return None, None
    lid = mh.rolling(N).max().shift(1)
    ceil = None; blow = None; armed = False
    age = 0; prev = None
    for i in range(n):
        li = lid.iloc[i]
        if li != li:               # NaN
            prev = li; age = 0; continue
        age = age + 1 if (prev is not None and li == prev) else 0
        prev = li
        established = age >= min_flat
        c = mc.iloc[i]; loo = ml.iloc[i]
        if established and c < li:
            if not armed:
                blow = loo; armed = True
            ceil = li if ceil is None else max(ceil, li)
            blow = min(blow, loo)
        if armed and blow is not None and c < blow:    # failed base — broke DOWN out of it
            armed = False; ceil = None; blow = None
        if armed and ceil is not None and c > ceil:    # cleared the ceiling — retire the box
            armed = False; ceil = None; blow = None
    return (ceil, blow) if armed else (None, None)


def _monthly_rch(mh, N=8, min_below=2):
    """RC-H level — the prior MONTHLY swing high that capped price for >= min_below
    completed months and is the nearest overhead resistance (or just-cleared level).
    No flat-base requirement, so it catches stair-step leaders MoBO misses. Returns the
    level or None. Requires the high to have been set >= min_below months ago (it HELD as
    resistance) — a smooth ramp making a fresh high every month yields None (no held high
    to break), which is the noise we want to avoid."""
    h = mh.dropna()
    if len(h) < N + 2:
        return None
    completed = h.iloc[:-1]                 # drop the developing (current) month
    window = completed.iloc[-N:]
    level = float(window.max())
    pos = int(window.values.argmax())
    months_since = len(window) - 1 - pos
    if months_since < min_below or level <= 0:
        return None
    return level


def _rsi(close, n=14):
    """Wilder's 14-day RSI of the daily close — the latest value."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, float("nan"))
    val = 100 - 100 / (1 + rs.iloc[-1])
    return float(val) if val == val else 50.0


def _daytrade_picks(data, cands, market_ok, top, adv_floor=2.0e7):
    """DAY-TRADE focus — a liquid leader / mega-cap AT a defended key level RIGHT NOW.
    Mirrors how the user trades it: AAPL bouncing from its monthly RC reclaim, MSFT from
    monthly support — a mega-cap defending a KEY level intraday. Three qualifiers, ranked
    by how MAJOR the level is (the bigger the timeframe, the higher the conviction):
      1. defending a key support — monthly low > 30w MA > weekly low > 10w MA > prior-day
         low (price holding just above it = the bounce zone),
      2. deep-oversold bounce — daily RSI <= 32 (the "mega-tech at 30 RSI" zone),
      3. coiling just under a key resistance (PWH / recent high) about to break.
    Liquidity-gated (>= adv_floor $/day) so the picks are actually day-tradeable."""
    out = []
    multi = len(cands) > 1
    for sym in cands:
        try:
            if sym.endswith("-USD"):            # crypto trades its own path — equities only here
                continue
            df = data[sym] if multi else data
            c = df["Close"].dropna(); h = df["High"].dropna()
            lo = df["Low"].dropna(); v = df["Volume"].dropna()
            if len(c) < 60:
                continue
            price = float(c.iloc[-1])
            advdol = float((c * v).tail(20).mean())
            if advdol < adv_floor:                      # too illiquid to day-trade
                continue
            rsi = _rsi(c, 14)
            wkc = c.resample("W").last().dropna()
            sma10w = float(wkc.rolling(10).mean().iloc[-1]) if len(wkc) >= 10 else None
            sma30w = float(wkc.rolling(30).mean().iloc[-1]) if len(wkc) >= 30 else None
            wlo = lo.resample("W").min().dropna()
            pwl = float(wlo.iloc[-2]) if len(wlo) >= 2 else None
            mlo = lo.resample("ME").min().dropna()
            pml = float(mlo.iloc[-2]) if len(mlo) >= 2 else None
            pdl = float(lo.iloc[-2])
            whi = h.resample("W").max().dropna()
            pwh = float(whi.iloc[-2]) if len(whi) >= 2 else None
            rhi = float(h.tail(20).max())

            # 1) defended key support — the MOST-MAJOR level price is holding just above.
            band = 0.018
            supports = [("the monthly low", pml, 100), ("the 30-week MA", sma30w, 82),
                        ("the weekly low", pwl, 76), ("the 10-week MA", sma10w, 56),
                        ("the prior-day low", pdl, 42)]
            defended = None
            for nm, lvl, wt in supports:
                if lvl and lvl > 0 and lvl <= price <= lvl * (1 + band):
                    defended = (nm, lvl, wt)
                    break
            oversold = rsi <= 32
            band2 = 0.025
            res = min([r for r in (pwh, rhi) if r and r > price], default=None)
            breakout = res is not None and (res - price) / price <= band2
            if not (defended or oversold or breakout):
                continue

            liq = math.log10(max(advdol, 1.0))          # ~7 ($10M) … ~10 ($10B)
            score = liq * 2.0
            reasons = []
            if defended:
                score += defended[2]
            if oversold:
                score += 60 + max(0.0, 32 - rsi) * 2.0
            if breakout:
                score += 50
            # primary setup (for the card) — a DEEP oversold (RSI <= 28) headlines even if
            # it's also at a support; otherwise defense (most-major level) → oversold → breakout.
            if defended and not (oversold and rsi <= 28):
                nm, lvl, _ = defended
                setup, key_lvl = "support defense", lvl
                reasons.append(f"defending {nm} ${lvl:.2f} ({(price - lvl) / lvl * 100:+.1f}% above)")
                stop = round(lvl * 0.985, 2)
                tgt = res or rhi
                entry = price
            elif oversold:
                setup, key_lvl = "oversold bounce", price
                reasons.append(f"daily RSI {rsi:.0f} — deep oversold bounce zone")
                stop = round(float(lo.tail(5).min()) * 0.995, 2)
                tgt = sma10w or rhi
                entry = price
            else:
                setup, key_lvl = "breakout watch", res
                reasons.append(f"coiling {(res - price) / price * 100:.1f}% under ${res:.2f} — about to break")
                stop = round(float(lo.tail(5).min()), 2)
                tgt = None
                entry = res
            if oversold and setup != "oversold bounce":
                reasons.append(f"daily RSI {rsi:.0f} (oversold)")
            if defended and setup != "support defense":
                reasons.append(f"at {defended[0]} ${defended[1]:.2f}")
            if breakout and setup != "breakout watch" and res:
                reasons.append(f"room to ${res:.2f} overhead")
            reasons.append(f"${advdol / 1e6:.0f}M/day — liquid")
            out.append({
                "symbol": sym, "score": round(score, 1), "type": "DAY", "setup": setup,
                "price": round(price, 2), "level": round(key_lvl, 2), "entry": round(entry, 2),
                "stop": stop, "target": round(tgt, 2) if tgt else None, "rsi": round(rsi),
                "position": "Full" if market_ok else "Half", "reasons": reasons,
            })
        except Exception:
            continue
    out.sort(key=lambda p: -p["score"])
    return out[:top]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--zone", type=float, default=5.0, help="buy-zone half-width % around the breakout level")
    ap.add_argument("--persist", action="store_true", help="write the report straight to market_reports (DB, offline)")
    ap.add_argument("--publish", action="store_true", help="POST to the API → persist + PUSH to all users (uses API_BASE/API_TOKEN)")
    args = ap.parse_args()

    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        sys.exit("Set DATABASE_URL.")
    import yfinance as yf

    cands = _watchlist(dsn)
    if not cands:
        print(json.dumps({"market": "unknown", "picks": [], "detail": "empty watchlist"}))
        return

    # Market health — SPY above its daily 8 AND 21 EMA = healthy. Modulates SIZE, not picks.
    spy = yf.download("SPY", period="3mo", interval="1d", progress=False, auto_adjust=False)
    spy_close = spy["Close"].dropna()
    spy_close = spy_close.iloc[:, 0] if hasattr(spy_close, "columns") else spy_close
    market_ok = bool(spy_close.iloc[-1] > spy_close.ewm(span=8).mean().iloc[-1]
                     and spy_close.iloc[-1] > spy_close.ewm(span=21).mean().iloc[-1])

    # Daily (15mo so the 200-DMA Stage-2 check has 200 bars) + monthly (8y) for the levels.
    data = yf.download(cands, period="15mo", interval="1d", progress=False,
                       auto_adjust=False, group_by="ticker", threads=True)
    mdata = yf.download(cands, period="8y", interval="1mo", progress=False,
                        auto_adjust=False, group_by="ticker", threads=True)

    picks = []
    for sym in cands:
        try:
            df = data[sym] if len(cands) > 1 else data
            c = df["Close"].dropna(); v = df["Volume"].dropna(); lo = df["Low"].dropna()
            if len(c) < 200:
                continue
            price = float(c.iloc[-1])
            try:
                mdf = mdata[sym] if len(cands) > 1 else mdata
                mh = mdf["High"].dropna(); ml = mdf["Low"].dropna(); mc = mdf["Close"].dropna()
            except Exception:
                continue

            # The two patterns, as candidate levels. Pick whichever the DAILY price is
            # actually AT (in zone) — coiling just under or just cleared, NOT extended.
            # Prefer MoBO (flat base = higher conviction) when both are in zone, so the
            # far one never shadows an in-zone break.
            box_level, box_low = _monthly_box(mh, ml, mc)
            rch_level = _monthly_rch(mh)
            cands_lv = []
            if box_level is not None:
                cands_lv.append(("MoBO", box_level, box_low))
            if rch_level is not None:
                cands_lv.append(("RC-H", rch_level, None))
            in_zone = [x for x in cands_lv if -args.zone <= (price - x[1]) / x[1] * 100.0 <= args.zone]
            if not in_zone:
                continue                         # no breakout in zone → skip (extended/none)
            in_zone.sort(key=lambda x: (0 if x[0] == "MoBO" else 1, abs((price - x[1]) / x[1])))
            kind, level, base_low = in_zone[0]
            dist_pct = (price - level) / level * 100.0
            stage2 = price > float(c.rolling(200).mean().iloc[-1])
            if not stage2:
                continue

            sma50 = float(c.rolling(50).mean().iloc[-1])
            vol_avg = float(v.rolling(50).mean().iloc[-1])
            vol_now = float(v.iloc[-1])
            vol_surge = vol_avg > 0 and vol_now > vol_avg * 1.3
            swing_low = float(lo.iloc[-10:].min())
            chg = (price / float(c.iloc[-2]) - 1.0) * 100.0
            cleared = dist_pct >= -0.5          # at/above the level = breaking; below = coiling

            # Stop: under the base / broken level, tightened to the recent swing or 50-DMA.
            floor = base_low if base_low else level * 0.93
            stop = max(swing_low, min(sma50, max(floor, level * 0.93)))

            score = (60 if kind == "MoBO" else 45) + (15 if vol_surge else 0) \
                + max(0.0, 8 - abs(dist_pct)) + (8 if cleared else 0)

            reasons = []
            if kind == "MoBO":
                reasons.append(f"MoBO — locked monthly box ceiling ${level:.2f} "
                               + ("just cleared" if cleared else f"{abs(dist_pct):.1f}% overhead"))
            else:
                reasons.append(f"monthly RC-H — prior monthly high ${level:.2f} (held for months) "
                               + ("breaking now" if cleared else f"{abs(dist_pct):.1f}% below"))
            reasons.append(f"buy zone ${level:.2f}–${level*(1+args.zone/100):.2f}")
            if vol_surge:
                reasons.append(f"volume {vol_now/vol_avg:.1f}× avg")
            reasons.append("Stage 2 (above the 200-day)")

            picks.append({
                "symbol": sym, "score": round(score, 1), "pattern": kind, "type": "SWING",
                "price": round(price, 2), "buy_point": round(level, 2),
                "buy_range": [round(level, 2), round(level * (1 + args.zone / 100), 2)],
                "state": "breaking" if cleared else "coiling",
                "position": "Full" if (market_ok and kind == "MoBO" and vol_surge) else "Half",
                "stop": round(stop, 2), "chg_pct": round(chg, 2), "reasons": reasons,
            })
        except Exception:
            continue

    # Rank swing: conviction + volume + proximity (in score). Tie-break MoBO first.
    picks.sort(key=lambda p: (-p["score"], 0 if p["pattern"] == "MoBO" else 1))
    swing = picks[:args.top]
    # DAY-TRADE focus — liquid mega-caps defending a key level / oversold / near a breakout.
    daytrade = _daytrade_picks(data, cands, market_ok, args.top)

    date = datetime.utcnow().strftime("%Y-%m-%d")
    L = [f"# Today's Focus — {date}", ""]
    L.append(f"Market: {'🟢 healthy (SPY above 8 & 21 EMA)' if market_ok else '🔴 weak — be selective'}")
    L.append("")
    L.append("## Swing — monthly breakout (MoBO + RC-H)")
    if not swing:
        L.append("_No watchlist name is at a monthly breakout today — nothing to chase. Patience._")
    for p in swing:
        L.append(f"### {p['symbol']} — {p['pattern']} · buy ${p['buy_point']} "
                 f"(range ${p['buy_range'][0]}–${p['buy_range'][1]}) · {p['position']} size")
        for r in p["reasons"]:
            L.append(f"- {r}")
        L.append(f"- stop ${p['stop']} · price now ${p['price']}")
        L.append("")
    L.append("## Day-Trade — key level defended (mega-cap bounce)")
    if not daytrade:
        L.append("_No liquid leader is at a key level today._")
    for p in daytrade:
        tgt = f" · target ${p['target']}" if p.get("target") else ""
        L.append(f"### {p['symbol']} — {p['setup']} · entry ${p['entry']} · {p['position']} size")
        for r in p["reasons"]:
            L.append(f"- {r}")
        L.append(f"- stop ${p['stop']}{tgt} · price now ${p['price']}")
        L.append("")
    report = "\n".join(L)
    print(report)
    print("\n---JSON---")
    print(json.dumps({"market_ok": market_ok, "candidates": len(cands), "swing": swing, "daytrade": daytrade}))

    # STORED body = structured JSON so the app renders rich cards (clickable → Trading).
    # "picks" = swing kept for any older reader; the new frontend reads swing + daytrade.
    body_json = json.dumps({"date": date, "market_ok": market_ok,
                            "swing": swing, "daytrade": daytrade, "picks": swing})

    if args.publish:
        import urllib.request
        base = os.getenv("API_BASE", "https://tradesignalwithai.com").rstrip("/")
        tok = os.getenv("API_TOKEN")
        if not tok:
            sys.exit("--publish needs API_TOKEN (and optional API_BASE).")
        allp = swing + daytrade
        syms = ", ".join(p["symbol"] for p in allp)
        push_title = ("📋 Today's focus: " + syms) if allp else "📋 No setups in focus today"
        push_body = "Swing breakouts + day-trade key levels — tap for the plan." if allp else "Nothing to chase. Patience."
        data = json.dumps({"kind": "morning_focus", "body": body_json, "session_date": date,
                           "push_title": push_title, "push_body": push_body}).encode()
        req = urllib.request.Request(base + "/api/v1/intel/reports/publish", data=data,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print("[published]", json.load(r))
        except Exception as e:
            sys.exit(f"publish failed: {str(e)[:160]}")
    elif args.persist:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=15)
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO market_reports (kind, session_date, body, created_at) "
                        "VALUES ('morning_focus', %s, %s, NOW()) "
                        "ON CONFLICT (kind, session_date) DO UPDATE SET body=EXCLUDED.body, created_at=NOW()",
                        (date, body_json))
            conn.commit(); cur.close()
            print(f"[persisted to market_reports kind=morning_focus session_date={date}]")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
