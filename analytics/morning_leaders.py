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
    """Scan the MASTER watchlist account (the curated platform universe), NOT the union of
    every user's ad-hoc adds. Falls back to the full union if the master account is absent."""
    import psycopg2
    conn = psycopg2.connect(dsn, connect_timeout=15)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower('master@busytradersdesk')")
    row = cur.fetchone()
    if row:
        cur.execute("SELECT DISTINCT UPPER(symbol) FROM watchlist "
                    "WHERE user_id=%s AND symbol IS NOT NULL AND symbol<>''", (row[0],))
    else:
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


def _rsi_series(close, n=14):
    """Wilder's 14-day RSI as a SERIES — used to detect the 30-reclaim (was <30, now ≥30)."""
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


def _daytrade_picks(data, cands, market_ok, top, adv_floor=2.0e7, live_px=None):
    """TODAY'S FOCUS — top `top`, a MIX of three setups (user 2026-06-30):
      • RSI-30 reclaim — daily RSI was oversold (<30 in the last 5d) and crossed back
        ABOVE 30, turning up → the bottom is in (NOT a still-falling oversold).
      • 200-EMA hold — price defending the daily 200-EMA as support (just above it).
      • Breakout / gap-and-go — gapped over the prior-day high and holding, or cleared
        the recent high with momentum.
    Liquidity-gated (≥ adv_floor $/day). The three buckets are INTERLEAVED so the five
    picks are a MIX (a turn + a hold + a breakout), not five of one kind."""
    buckets = {"reclaim_30": [], "ema200_hold": [], "breakout": []}
    multi = len(cands) > 1
    pos = "Full" if market_ok else "Half"
    for sym in cands:
        try:
            if sym.endswith("-USD"):            # crypto trades its own path — equities only here
                continue
            df = data[sym] if multi else data
            c = df["Close"].dropna(); h = df["High"].dropna()
            lo = df["Low"].dropna(); v = df["Volume"].dropna(); o = df["Open"].dropna()
            if len(c) < 60:
                continue
            _lp = (live_px or {}).get(sym)
            price = _lp if _lp else float(c.iloc[-1])
            advdol = float((c * v).tail(20).mean())
            if advdol < adv_floor:                      # too illiquid to day-trade
                continue
            liq = math.log10(max(advdol, 1.0))          # ~7 ($10M) … ~10 ($10B)
            rsi_s = _rsi_series(c, 14)
            rsi = float(rsi_s.iloc[-1]) if rsi_s.iloc[-1] == rsi_s.iloc[-1] else 50.0
            rsi_prev = float(rsi_s.iloc[-2]) if len(rsi_s) >= 2 and rsi_s.iloc[-2] == rsi_s.iloc[-2] else rsi
            rsi_min5 = float(rsi_s.tail(6).iloc[:-1].min())          # min RSI of the prior 5 days
            rhi = float(h.tail(20).max())
            pdh = float(h.iloc[-2]); pdl = float(lo.iloc[-2])
            prior_close = float(c.iloc[-2]); open_today = float(o.iloc[-1])
            ema200 = float(c.ewm(span=200, adjust=False).mean().iloc[-1]) if len(c) >= 200 else None
            recent_stop = round(float(lo.tail(5).min()) * 0.995, 2)
            advtxt = f"${advdol / 1e6:.0f}M/day — liquid"

            # ── 1) RSI-30 RECLAIM — was oversold, crossed back above 30, turning up
            if rsi_min5 < 30 <= rsi <= 45 and rsi >= rsi_prev:
                tgt = ema200 if (ema200 and ema200 > price) else rhi
                buckets["reclaim_30"].append({
                    "symbol": sym, "score": round(liq * 2 + 70 + max(0.0, 40 - rsi), 1),
                    "type": "DAY", "setup": "RSI-30 reclaim", "price": round(price, 2),
                    "level": round(price, 2), "entry": round(price, 2), "stop": recent_stop,
                    "target": round(tgt, 2) if tgt else None, "rsi": round(rsi), "position": pos,
                    "reasons": [f"daily RSI reclaimed 30 (now {rsi:.0f}, was {rsi_min5:.0f}) — the turn is in",
                                advtxt],
                })
                continue

            # ── 2) 200-EMA HOLD — defending the daily 200-EMA just above
            if ema200 and ema200 <= price <= ema200 * 1.025:
                tgt = min([r for r in (pdh, rhi) if r and r > price], default=None)
                buckets["ema200_hold"].append({
                    "symbol": sym, "score": round(liq * 2 + 60 + (1.025 - price / ema200) * 800, 1),
                    "type": "DAY", "setup": "200-EMA hold", "price": round(price, 2),
                    "level": round(ema200, 2), "entry": round(price, 2), "stop": round(ema200 * 0.99, 2),
                    "target": round(tgt, 2) if tgt else None, "rsi": round(rsi), "position": pos,
                    "reasons": [f"holding the 200-EMA ${ema200:.2f} ({(price - ema200) / ema200 * 100:+.1f}% above)",
                                advtxt],
                })
                continue

            # ── 3) BREAKOUT / GAP-AND-GO — over the prior-day high + holding, or cleared the recent high
            gapped = price > pdh and price >= prior_close
            broke_pdh = price > pdh and price > prior_close * 1.005
            broke_recent = price >= rhi * 0.999
            if (gapped or broke_pdh or broke_recent) and price > prior_close:
                kind = "gap-and-go" if gapped else "breakout"
                reason = (f"gapped over the prior-day high ${pdh:.2f}, holding" if gapped
                          else f"broke the prior-day high ${pdh:.2f}" if broke_pdh
                          else f"cleared the 20-day high ${rhi:.2f}")
                buckets["breakout"].append({
                    "symbol": sym, "score": round(liq * 2 + 50 + (15 if gapped else 0), 1),
                    "type": "DAY", "setup": kind, "price": round(price, 2), "level": round(pdh, 2),
                    "entry": round(price, 2),
                    "stop": round(pdh * 0.998, 2) if gapped else round(pdl, 2),
                    "target": None, "rsi": round(rsi), "position": pos,
                    "reasons": [reason, advtxt],
                })
                continue
        except Exception:
            continue
    for b in buckets:
        buckets[b].sort(key=lambda p: -p["score"])
    # INTERLEAVE — one from each bucket, then the seconds, … so the top `top` are a mix.
    picks, i, order = [], 0, ("breakout", "reclaim_30", "ema200_hold")
    while len(picks) < top and any(len(buckets[b]) > i for b in order):
        for b in order:
            if len(picks) < top and len(buckets[b]) > i:
                picks.append(buckets[b][i])
        i += 1
    return picks


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

    # Live/pre-market price overlay — the daily close is STALE at 8:35 ET (a gapped name still
    # shows yesterday's close, e.g. AVGO 360 while pre-market is 376). Use the last 1m (prepost)
    # print so entries + setup checks reflect the pre-market; falls back to the daily close.
    live_px: dict = {}
    try:
        _ld = yf.download(cands, period="1d", interval="1m", prepost=True, progress=False,
                          auto_adjust=False, group_by="ticker", threads=True)
        for _s in cands:
            try:
                _col = (_ld[_s]["Close"] if len(cands) > 1 else _ld["Close"]).dropna()
                if len(_col):
                    live_px[_s] = float(_col.iloc[-1])
            except Exception:
                pass
    except Exception:
        pass

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
    daytrade = _daytrade_picks(data, cands, market_ok, args.top, live_px=live_px)

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
    L.append("## Today's Focus — the turn · the hold · the breakout")
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
