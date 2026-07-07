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


def _daily_ema50_floor(symbols):
    """{symbol: bool} — is price above its daily 50-EMA? The swing TRUST FLOOR: below the 50-EMA we
    don't trust a swing (user 2026-07-07 — stocks chop around the deeper MAs)."""
    import yfinance as yf
    try:
        d = yf.download(symbols, period="1y", interval="1d", progress=False,
                        auto_adjust=True, group_by="ticker", threads=True)
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
            entry = ceil; stop = blow; risk = entry - stop
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
                    "monthly base breakout — the 'catch the next MU/SNDK' engine (validated +0.56R)",
                ],
            })
    mb.sort(key=lambda x: x["symbol"])
    return mb


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
            stop = min(L[i], s30[i]) * 0.99
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


def emit(dsn, cc, bb, mr=None, mb=None):
    """Insert one alert row per NEW swing signal (deduped ~weekly) so the Performance page scores them.
    user_id = master (the scan-universe owner); the types default OFF so nothing is delivered to users."""
    import psycopg2
    from datetime import date, timedelta
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE lower(email)=lower(%s)", (MASTER_EMAIL,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return 0
    mid = row[0]
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=5)).isoformat()  # weekly setup, daily scan -> one row/week
    inserted = 0
    for sig, atype in ([(x, "character_change") for x in cc if x.get("actionable")] + [(x, "base_buy") for x in bb if x.get("actionable")] + [(x, "monthly_ma_reclaim") for x in (mr or []) if x.get("actionable")] + [(x, "monthly_box") for x in (mb or []) if x.get("actionable")]):
        try:
            cur.execute("SELECT 1 FROM alerts WHERE user_id=%s AND UPPER(symbol)=%s AND alert_type=%s AND session_date>=%s LIMIT 1",
                        (mid, sig["symbol"], atype, cutoff))
            if cur.fetchone():
                continue
            cur.execute(
                "INSERT INTO alerts (user_id, symbol, alert_type, direction, price, entry, stop, target_1, session_date, trade_type, created_at) "
                "VALUES (%s,%s,%s,'BUY',%s,%s,%s,%s,%s,'swing',NOW())",
                (mid, sig["symbol"], atype, sig["entry"], sig["entry"], sig["stop"], sig["target"], today))
            inserted += 1
        except Exception:
            conn.rollback()
    conn.commit()
    conn.close()
    return inserted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true", help="upsert into market_reports[swing_setups]")
    ap.add_argument("--emit", action="store_true", help="insert scored alert rows (Performance page)")
    args = ap.parse_args()
    dsn = _dsn()
    syms = sorted(set(_master_symbols(dsn)) | set(_ltf_symbols(dsn)))   # master + LTF discovery pool
    if not syms:
        raise SystemExit("no master symbols")
    floor = _daily_ema50_floor(syms)                                    # daily 50-EMA trust floor
    cc, bb = scan(syms, floor)
    mdata = _monthly(syms)                                              # one monthly download for both monthly scanners
    mr = scan_monthly(syms, floor, mdata)
    mb = scan_mobo(syms, floor, mdata)
    body = {"character_change": cc, "base_buy": bb, "monthly_ma_reclaim": mr, "mobo_breakout": mb, "universe": len(syms)}
    print(f"scanned {len(syms)} names — CC: {len(cc)}, Bases: {len(bb)}, Monthly MA reclaim: {len(mr)}, MoBO breakout: {len(mb)}")
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
        print(f"[emitted {emit(dsn, cc, bb, mr, mb)} new swing alerts]")


if __name__ == "__main__":
    main()
