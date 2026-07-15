"""Weekly swing scanner — Character Change + Buying in Bases.

Two setups validated in Python (specs/swing-patterns/spec.md) — R-based, in/out-of-sample:
  • Character Change — rare weekly reversal (+0.48R): downtrend → volume surge + first 10w
    reclaim + higher swing low. Entry = close, stop = below the 30w MA.
  • Buying in Bases   — proven uptrend digesting, right side lifting (+0.22R): above 30w +
    prior run + sideways + tightening range + higher lows + volume drying. Stop = below the
    higher low.

Runs EOD on the MASTER universe (the ~82-name discovery list), on WEEKLY bars. Reports the
CURRENT signals (triggers on the last closed weekly bar). Publishes to market_reports so the
app shows them; also prints JSON for the cron log.

    DATABASE_URL=... python3 triage-agent/swing_scan.py --persist
"""
import argparse
import json
import os
import warnings

warnings.filterwarnings("ignore")

MASTER_EMAIL = "master@busytradersdesk"


def _broad_symbols():
    """Static broad universe (S&P 500 + Nasdaq 100 + growth leaders) so swing setups are discovered
    across a WIDE pool, not just the ~72-name master watchlist. See broad_universe.py."""
    try:
        from broad_universe import BROAD_UNIVERSE
    except Exception:
        try:
            from .broad_universe import BROAD_UNIVERSE
        except Exception:
            return []
    return [s for s in BROAD_UNIVERSE if "-USD" not in s]


def _ibd_symbols():
    """IBD 50 + Sector Leaders (the growth/earnings CAN SLIM screen) from the .xls exports, if present.
    IBD/MarketSurge .xls put the tickers under a 'Symbol' header a few rows down (header=None + find the
    row). Laptop-only — returns [] in prod, where the master watchlist carries these via the sync."""
    out = set()
    here = os.path.dirname(__file__)
    roots = [os.path.join(here, ".."), os.path.join(here, "..", "..")]   # trade-analytics + its parent
    for fn in ("ibd50.xls", "sectorleaders.xls"):
        for root in roots:
            p = os.path.join(root, fn)
            if not os.path.exists(p):
                continue
            try:
                import pandas as pd
                df = pd.read_excel(p, header=None)
                hdr = next(i for i in range(min(15, len(df)))
                           if "Symbol" in [str(x).strip() for x in df.iloc[i].tolist()])
                col = [str(x).strip() for x in df.iloc[hdr].tolist()].index("Symbol")
                for v in df.iloc[hdr + 1:, col].dropna():
                    s = str(v).upper().strip()
                    if s and s.isascii() and 1 < len(s) <= 6 and s.replace("-", "").isalpha():
                        out.add(s)
            except Exception:
                pass
            break
    return out


def _rs_rank(symbols, ddata):
    """IBD-style relative strength — a recent-weighted blend of 3/6/12-month price return. Returns
    {symbol: score}; higher = stronger leader. Used to keep only the top performers from the broad pool."""
    out = {}
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (ddata[s] if multi else ddata).dropna()
        except Exception:
            continue
        C = df["Close"].values
        if len(C) < 130:
            continue
        c = float(C[-1])
        r3 = c / C[-63] - 1 if len(C) >= 63 else 0.0
        r6 = c / C[-126] - 1 if len(C) >= 126 else 0.0
        r12 = c / C[-252] - 1 if len(C) >= 252 else r6
        out[s] = 0.4 * r3 + 0.3 * r6 + 0.3 * r12
    return out


def _dsn():
    v = os.environ.get("DATABASE_URL")
    if v:
        return v
    for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
        if line.startswith("DATABASE_URL"):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("no DATABASE_URL")


def _ltf_symbols(dsn):
    """Long Term Finders discovery names (emerging + core leaders) from market_reports."""
    import psycopg2, json
    try:
        conn = psycopg2.connect(dsn); cur = conn.cursor()
        cur.execute("SELECT body FROM market_reports WHERE kind='long_term_finders' ORDER BY created_at DESC LIMIT 1")
        r = cur.fetchone(); conn.close()
        if not r:
            return []
        d = json.loads(r[0])
        out = []
        for it in (d.get("finders") or []):
            sym = (it.get("symbol") or "").upper().strip()
            if sym and "-USD" not in sym:
                out.append(sym)
        return out
    except Exception:
        return []


def _master_symbols(dsn):
    import psycopg2
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
    row = cur.fetchone()
    if not row:
        return []
    cur.execute(
        "SELECT DISTINCT UPPER(symbol) FROM watchlist WHERE user_id=%s AND symbol NOT LIKE '%%-USD'",
        (row[0],),
    )
    syms = sorted(x[0] for x in cur.fetchall())
    conn.close()
    return syms


def _r2(x):
    return round(float(x), 2)


def _ema(a, n):
    import numpy as np
    k = 2.0 / (n + 1); out = np.full(len(a), np.nan)
    if len(a) < n:
        return out
    out[n - 1] = a[:n].mean()
    for i in range(n, len(a)):
        out[i] = a[i] * k + out[i - 1] * (1 - k)
    return out


def _daily(symbols):
    import yfinance as yf
    return yf.download(symbols, period="2y", interval="1d", progress=False,
                       auto_adjust=True, group_by="ticker", threads=True)


def _daily_ema50_floor(symbols, data=None):
    """{symbol: bool} — is price above its daily 50-EMA? The swing TRUST FLOOR: below the 50-EMA we
    don't trust a swing (user 2026-07-07 — stocks chop around the deeper MAs)."""
    try:
        d = _daily(symbols) if data is None else data
    except Exception:
        return {s: True for s in symbols}   # fail-open on a data hiccup — don't block the whole scan
    out = {}
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (d[s] if multi else d).dropna()
            C = df["Close"].values
            if len(C) < 55:
                out[s] = False; continue
            out[s] = bool(C[-1] > _ema(C, 50)[-1])
        except Exception:
            out[s] = False
    return out


def _monthly(symbols):
    import yfinance as yf
    return yf.download(symbols, period="max", interval="1mo", progress=False,
                       auto_adjust=True, group_by="ticker", threads=True)


def scan_mobo(symbols, floor, data=None):
    """MoBO — monthly BOX breakout, validated +0.56R (64% win). Price closes above a LOCKED flat
    multi-month ceiling (the base) + Stage-2 (above the 10-month EMA) + a volume pickup, above the
    daily 50-EMA floor. Entry = the ceiling clear, stop = the base low. The 'catch the next MU/SNDK'."""
    import numpy as np
    data = _monthly(symbols) if data is None else data
    N, MINFLAT = 4, 3
    mb = []
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (data[s] if multi else data).dropna()
        except Exception:
            continue
        if len(df) < 12 or not floor.get(s, False):
            continue
        C = df["Close"].values; H = df["High"].values; L = df["Low"].values; V = df["Volume"].values
        e10 = _ema(C, 10); i = len(C) - 1
        if i < N + 1 or e10[i] != e10[i]:
            continue
        ceil = float(max(H[i - N:i])); blow = float(min(L[i - N:i]))
        if ceil <= 0 or blow <= 0:
            continue
        depth = (ceil - blow) / ceil
        flat = float(max(H[i - MINFLAT:i])) <= ceil * 1.005 and (H[i - N:i].max() - H[i - N:i].min()) / ceil < 0.10
        va = float(V[i - N:i].mean())
        brk = C[i] > ceil and C[i - 1] <= ceil and C[i] > e10[i] and V[i] > va   # close clears + Stage-2 + volume
        if flat and brk and 0.03 <= depth <= 0.60:
            # TIGHT stop = 8% below the breakout ceiling — a monthly close back into the box fails it.
            # NOT the base low (deep boxes → ~21% risk; backtested worse: +0.95R @ 21% vs +1.15R @ 8%).
            entry = ceil; stop = round(ceil * 0.92, 2); risk = entry - stop
            if risk <= 0:
                continue
            mb.append({
                "symbol": s, "setup": "MoBO breakout", "type": "SWING",
                "entry": _r2(entry), "stop": _r2(stop), "target": _r2(entry + 2 * risk),
                "now": _r2(float(C[i])), "actionable": True,
                "status": "cleared the locked monthly base ceiling — position breakout",
                "reasons": [
                    f"closed above the locked flat {N}-month ceiling (${entry:.2f}) on volume",
                    "Stage-2 (above the 10-month EMA) + above the daily 50-EMA floor",
                    f"monthly base breakout — tight stop ${stop:.2f}, 8% below the ceiling (validated +1.15R)",
                ],
            })
    mb.sort(key=lambda x: x["symbol"])
    return mb


def scan_new_high(symbols, floor, data=None):
    """52-week-high breakout — validated +0.22R (61% still up at 1mo). Price CLOSES through its prior
    52-week high, in an uptrend (above the daily 50-EMA), on above-average volume. Entry = the breakout
    close, stop = the 10-day base low. Catches leaders breaking to new highs at the close (broader than
    the MoBO flat-box). Runs in the 4:25 PM EOD scan → on the FINAL close, ready for overnight research."""
    data = _daily(symbols) if data is None else data
    nh = []
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (data[s] if multi else data).dropna()
        except Exception:
            continue
        if len(df) < 260 or not floor.get(s, False):
            continue
        C = df["Close"].values; H = df["High"].values; L = df["Low"].values; V = df["Volume"].values
        i = len(C) - 1
        hi52 = float(max(H[i - 252:i]))                                 # prior 52-week high (excl today)
        vol = V[i] > 1.2 * V[max(0, i - 20):i].mean()
        if hi52 > 0 and C[i] > hi52 and C[i - 1] <= hi52 and vol:       # fresh close through the 52w high on volume
            # TIGHT structural stop = 3% below the reclaimed 52-week high — a close back under the level
            # it broke = failed breakout. NOT the 10-day base low (~21% away, invalidates the entry;
            # backtested worse: +0.14R @ 21.5% risk vs +0.20R @ 6.5% risk for the tight stop).
            entry = float(C[i]); stop = round(hi52 * 0.97, 2); risk = entry - stop
            if risk > 0:
                nh.append({
                    "symbol": s, "setup": "52-week high breakout", "type": "SWING",
                    "entry": _r2(entry), "stop": _r2(stop), "target": _r2(entry + 2 * risk),
                    "now": _r2(entry), "actionable": True,
                    "status": "closed through the 52-week high on volume — fresh new-high breakout",
                    "reasons": [
                        f"cleared the 52-week high ${hi52:.2f} at the close",
                        "uptrend (above the daily 50-EMA) + above-average volume",
                        f"tight stop ${stop:.2f} — a close back below the reclaimed high fails it (validated +0.20R)",
                    ],
                })
    nh.sort(key=lambda x: x["symbol"])
    return nh


def scan_monthly(symbols, floor, data=None):
    """Monthly MA reclaim (M8/M21) — validated +0.36R. Price tags a RISING monthly 8-EMA (or 21-EMA)
    and holds above it, in an uptrend (above a rising monthly 21-EMA) AND above the daily 50-EMA floor.
    Fires ONLY the reclaim (at the zone); extended names (ANET) / below-MA names (PLTR) are NOT emitted."""
    data = _monthly(symbols) if data is None else data
    mr = []
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (data[s] if multi else data).dropna()
        except Exception:
            continue
        if len(df) < 30:
            continue
        C = df["Close"].values; H = df["High"].values
        e8 = _ema(C, 8); e21 = _ema(C, 21)
        i = len(C) - 1
        if e8[i] != e8[i] or e21[i] != e21[i]:
            continue
        price = float(C[i])
        up = price > e21[i] and (e21[i] - e21[i - 1]) > 0        # above a RISING monthly 21-EMA
        if not up or not floor.get(s, False):                    # 50-EMA trust floor
            continue
        for ma, tag in ((float(e8[i]), "M8"), (float(e21[i]), "M21")):
            if ma <= 0:
                continue
            dist = (price / ma - 1) * 100.0
            if -1.0 <= dist <= 4.0:                              # AT the MA (tagged + holding) = reclaim
                stop = ma * 0.97                                 # a monthly close below the MA
                target = max(float(max(H[max(0, i - 12):i + 1])), ma * 1.12)
                if target > ma:
                    mr.append({
                        "symbol": s, "setup": f"Monthly {tag} reclaim", "type": "SWING",
                        "entry": _r2(ma), "stop": _r2(stop), "target": _r2(target),
                        "now": _r2(price), "actionable": True,
                        "status": f"at the monthly {tag} — buy the reclaim of a rising trend MA",
                        "reasons": [
                            f"reclaim/hold of the rising monthly {tag} (${ma:.2f}) in an uptrend",
                            "above the daily 50-EMA (swing trust floor)",
                            "longest-term trend support — a position hold (validated +0.36R)",
                        ],
                    })
                break                                           # one per symbol, prefer M8
    mr.sort(key=lambda x: x["symbol"])
    return mr


def scan(symbols, floor=None):
    """Return (character_change[], base_buy[]) — signals on the latest closed weekly bar."""
    import yfinance as yf

    data = yf.download(symbols, period="3y", interval="1wk", progress=False,
                       auto_adjust=True, group_by="ticker", threads=True)
    cc, bb = [], []
    multi = len(symbols) > 1
    for s in symbols:
        try:
            df = (data[s] if multi else data).dropna()
        except Exception:
            continue
        if len(df) < 45:
            continue
        C = df["Close"].values
        V = df["Volume"].values
        L = df["Low"].values
        H = df["High"].values
        s30 = df["Close"].rolling(30).mean().values
        s10 = df["Close"].rolling(10).mean().values
        va = df["Volume"].rolling(20).mean().values
        i = len(C) - 1  # latest (developing) weekly bar
        price = float(C[i])
        if price <= 0 or s30[i] != s30[i]:
            continue
        liq = (C[i] * V[i]) >= 30e6

        # ── Character Change ─────────────────────────────────────────────
        below = (C[i - 10:i] < s30[i - 10:i]).any()
        volsurge = V[i] > 1.7 * va[i]
        reclaim = C[i] > s10[i] and C[i - 1] <= s10[i - 1]
        upweek = C[i] > C[i - 1]
        hl_cc = L[max(0, i - 4):i + 1].min() > L[max(0, i - 12):i - 4].min()
        if below and volsurge and reclaim and upweek and hl_cc:
            stop = float(L[i]) * 0.99   # the RECLAIM week's low — lose the reversal bar's low = out (your "stop = reclaim low" rule; backtests same as min(low,30w) but never widens to a far-below 30w)
            if stop < price:
                cc.append({
                    "symbol": s, "setup": "Character Change", "type": "SWING",
                    "entry": _r2(price), "stop": _r2(stop),
                    "target": _r2(price + 2 * (price - stop)),
                    "now": _r2(price), "actionable": True, "status": "buy the reclaim (entry = this week's close)",
                    "reasons": [
                        "weekly reversal — first 10w reclaim off a downtrend",
                        f"volume {V[i] / va[i]:.1f}x its 20w average (institutional)",
                        "higher swing low (sellers exhausting)",
                    ],
                })

        # ── Buying in Bases ──────────────────────────────────────────────
        above = price > s30[i]
        ran = price > 1.25 * min(C[i - 40:i - 15])
        flat = abs(price / C[i - 10] - 1) < 0.12
        hl_bb = L[max(0, i - 3):i + 1].min() > L[max(0, i - 8):i - 3].min()
        vdry = V[max(0, i - 6):i + 1].mean() < 0.8 * V[max(0, i - 14):i - 6].mean()
        tight = (max(H[i - 6:i + 1]) - min(L[i - 6:i + 1])) < 0.85 * (max(H[i - 14:i - 6]) - min(L[i - 14:i - 6]))
        near_high = price >= 0.85 * max(H[max(0, i - 52):i + 1])                                   # a base sits NEAR the highs (not a deep pullback)
        tight_range = (max(H[max(0, i - 10):i + 1]) - min(L[max(0, i - 10):i + 1])) < 0.30 * price  # ...and is TIGHT (not a 59% range like IONQ)
        floor_ok = floor is None or floor.get(s, False)   # 50-EMA trust floor (CC is exempt — it's a reversal from below)
        if above and ran and flat and hl_bb and vdry and tight and liq and near_high and tight_range and floor_ok:
            hlow = float(L[max(0, i - 3):i + 1].min())     # the base's higher low = the pivot/support
            buy = hlow * 1.01                              # BUY the pullback to just above the pivot, not the top
            stop = hlow * 0.97                             # ~3% under the pivot — lose the base = out (TIGHT)
            base_high = float(max(H[max(0, i - 10):i + 1]))  # top of the base = first target / breakout level
            ext = (price / buy - 1) * 100                  # how far ABOVE the buy zone price sits now
            actionable = ext <= 4.0                         # price is AT the zone → fillable now
            if buy > stop and base_high > buy:
                bb.append({
                    "symbol": s, "setup": "Buying in Bases", "type": "SWING",
                    "entry": _r2(buy), "stop": _r2(stop), "target": _r2(base_high),
                    "now": _r2(price), "actionable": actionable,
                    "status": ("buy the zone — price is at support" if actionable
                               else f"extended +{ext:.0f}% — wait for a pullback to ${buy:.2f}"),
                    "reasons": [
                        "proven uptrend digesting — base right side lifting",
                        f"BUY the pullback to the higher low ${hlow:.2f} (not the top of the range)",
                        "tightening range + higher lows, volume drying up",
                    ],
                })
    cc.sort(key=lambda x: x["symbol"])
    bb.sort(key=lambda x: x["symbol"])
    return cc, bb


def emit(dsn, cc, bb, mr=None, mb=None, nh=None):
    """BROADCAST swing setups to EVERY user's Signals feed — swing alerts are rare + high-conviction, so
    they go to ALL users, not just watchers (user 2026-07-08: "only swing delivery goes to all users;
    they aren't a lot, but when they come they're solid"). Master-gated so each setup broadcasts once a
    week. Returns (inserted_rows, new_setups): new_setups is one (sig, atype) per setup broadcast THIS
    run — it drives the APNs + Telegram push in push_swing_alerts()."""
    import psycopg2
    from datetime import date, timedelta
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return 0, []
    mid = row[0]
    cur.execute("SELECT id FROM users WHERE id != %s", (mid,))   # every REAL user (exclude master universe acct)
    everyone = [r[0] for r in cur.fetchall()]
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=5)).isoformat()  # weekly setup, daily scan -> one broadcast/week
    inserted = 0
    new_setups = []
    # monthly_ma_reclaim ("monthly m8") emission REMOVED 2026-07-14 (user: mostly false/bad). mr is
    # still scanned for the report count, just no longer fired as an alert. Monthly BREAKOUT (MoBO) stays.
    for sig, atype in ([(x, "character_change") for x in cc if x.get("actionable")] + [(x, "base_buy") for x in bb if x.get("actionable")] + [(x, "monthly_box") for x in (mb or []) if x.get("actionable")] + [(x, "new_high_breakout") for x in (nh or []) if x.get("actionable")]):
        s = sig["symbol"]
        try:
            # one SELECT for who already has this setup this week; master row = the "already broadcast"
            # gate so each setup broadcasts + pushes exactly once.
            cur.execute("SELECT user_id FROM alerts WHERE UPPER(symbol)=%s AND alert_type=%s AND session_date>=%s",
                        (s, atype, cutoff))
            have = {r[0] for r in cur.fetchall()}
            if mid in have:
                continue                                     # already broadcast this week — skip + no re-push
            for uid in everyone + [mid]:
                if uid in have:
                    continue
                cur.execute(
                    "INSERT INTO alerts (user_id, symbol, alert_type, direction, price, entry, stop, target_1, session_date, trade_type, created_at) "
                    "VALUES (%s,%s,%s,'BUY',%s,%s,%s,%s,%s,'swing',NOW())",
                    (uid, s, atype, sig["entry"], sig["entry"], sig["stop"], sig["target"], today))
                inserted += 1
            new_setups.append((sig, atype))
        except Exception:
            conn.rollback()
    conn.commit()
    conn.close()
    return inserted, new_setups


def push_swing_alerts(dsn, new_setups):
    """Notify EVERY user of the swing setups emitted this run — APNs to all registered iOS devices
    (reusing the reports_store fan-out) + Telegram to every linked user. Each alert is labeled SWING and
    carries entry/stop/target + reasons (a longer-term hold). Best-effort; never raises."""
    if not new_setups:
        return
    import os, logging
    log = logging.getLogger("swing_scan")
    required = ("APNS_AUTH_KEY", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID")
    tokens = []
    try:
        import reports_store as _rs
        tokens = _rs._device_tokens()
    except Exception:
        log.exception("swing push: device-token lookup failed")
    if tokens and all(os.environ.get(k) for k in required):
        try:
            from aioapns import APNs, NotificationRequest, PushType
            import asyncio

            async def _fan():
                client = APNs(key=os.environ["APNS_AUTH_KEY"], key_id=os.environ["APNS_KEY_ID"],
                              team_id=os.environ["APNS_TEAM_ID"], topic=os.environ["APNS_BUNDLE_ID"],
                              use_sandbox=os.environ.get("APNS_USE_SANDBOX", "0") == "1")
                for sig, atype in new_setups:
                    title = f"\U0001F3AF SWING · {sig.get('setup', 'setup')}"
                    body = f"{sig['symbol']} — buy {sig['entry']}, stop {sig['stop']}, target {sig['target']} · hold for days"
                    message = {"aps": {"alert": {"title": title, "body": body}, "sound": "default", "thread-id": "swing"},
                               "data": {"type": "swing_alert", "symbol": sig["symbol"], "route": "/today?tab=focus"}}
                    for tok in tokens:
                        try:
                            await client.send_notification(NotificationRequest(device_token=tok, message=message, push_type=PushType.ALERT))
                        except Exception:
                            pass
            asyncio.run(_fan())
            log.info("swing push: APNs sent %d setup(s) to %d device(s)", len(new_setups), len(tokens))
        except ImportError:
            log.info("swing push: aioapns not installed, skipping APNs")
        except Exception:
            log.exception("swing push: APNs fan-out failed")
    try:
        _push_swing_telegram(dsn, new_setups)
    except Exception:
        log.exception("swing push: Telegram failed")


def _push_swing_telegram(dsn, new_setups):
    """Post each swing setup to every linked user's Telegram, labeled SWING with the entry reasons."""
    import os, psycopg2
    try:
        import requests
    except Exception:
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    conn = psycopg2.connect(dsn); cur = conn.cursor()
    cur.execute("SELECT telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL AND telegram_chat_id <> ''")
    chats = [r[0] for r in cur.fetchall()]
    conn.close()
    if not chats:
        return
    for sig, atype in new_setups:
        reasons = "\n".join(f"• {r}" for r in sig.get("reasons", []))
        text = (f"\U0001F3AF *SWING · {sig.get('setup','setup')}*\n"
                f"*{sig['symbol']}* — buy `{sig['entry']}`  stop `{sig['stop']}`  target `{sig['target']}`\n"
                f"_{sig.get('status','')}_\n{reasons}\n\n_Longer-term hold — valid while the thesis holds. Not financial advice._")
        for chat in chats:
            try:
                requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json={"chat_id": str(chat), "text": text, "parse_mode": "Markdown"}, timeout=10)
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true", help="upsert into market_reports[swing_setups]")
    ap.add_argument("--emit", action="store_true", help="insert scored alert rows (Performance page)")
    args = ap.parse_args()
    dsn = _dsn()
    keep = set(_master_symbols(dsn)) | set(_ltf_symbols(dsn)) | set(_ibd_symbols())   # curated names — always scanned
    broad = set(_broad_symbols())
    pool = sorted(keep | broad)
    if not pool:
        raise SystemExit("no symbols")
    ddata = _daily(pool)                                                # daily for RS rank + 50-EMA floor + new-high
    # Keep only the top-performer LEADERS from the broad S&P/NDX pool by relative strength (the curated
    # master/LTF/IBD names are always kept). SWING_RS_TOPN caps how many leaders (default 150).
    topn = int(os.environ.get("SWING_RS_TOPN", "150"))
    rs = _rs_rank(sorted(broad - keep), ddata)
    top_broad = set(sorted(rs, key=rs.get, reverse=True)[:topn])
    syms = sorted(keep | top_broad)                                     # final quality universe = curated + leaders
    floor = _daily_ema50_floor(syms, ddata)                            # daily 50-EMA trust floor
    cc, bb = scan(syms, floor)
    mdata = _monthly(syms)                                              # one monthly download for both monthly scanners
    mr = scan_monthly(syms, floor, mdata)
    mb = scan_mobo(syms, floor, mdata)
    nh = scan_new_high(syms, floor, ddata)
    body = {"character_change": cc, "base_buy": bb, "monthly_ma_reclaim": mr, "mobo_breakout": mb, "new_high_breakout": nh, "universe": len(syms), "pool": len(pool), "leaders": len(top_broad)}
    print(f"scanned {len(syms)} leaders (top-{topn} RS + curated, of {len(pool)} pool) — CC: {len(cc)}, Bases: {len(bb)}, Monthly MA reclaim: {len(mr)}, MoBO: {len(mb)}, New-high: {len(nh)}")
    print("---JSON---")
    print(json.dumps(body))
    if args.persist:
        import psycopg2
        from datetime import date
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS market_reports (
            kind TEXT NOT NULL, session_date TEXT NOT NULL, body TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(), PRIMARY KEY (kind, session_date))""")
        cur.execute(
            "INSERT INTO market_reports (kind, session_date, body) VALUES ('swing_setups', %s, %s) "
            "ON CONFLICT (kind, session_date) DO UPDATE SET body=EXCLUDED.body, created_at=NOW()",
            (date.today().isoformat(), json.dumps(body)))
        conn.commit()
        print(f"[persisted swing_setups {date.today().isoformat()}]")
    if args.emit:
        n, new_setups = emit(dsn, cc, bb, mr, mb, nh)
        print(f"[emitted {n} swing alert rows to ALL users · {len(new_setups)} new setup(s)]")
        push_swing_alerts(dsn, new_setups)
        if new_setups:
            print(f"[pushed {len(new_setups)} setup(s) via APNs + Telegram: {', '.join(s['symbol'] for s, _ in new_setups)}]")


if __name__ == "__main__":
    main()
