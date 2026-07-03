"""Week-1 Strategy Lab grading: evaluate every SENT alert on entry/stop only.
Two stop conventions per alert:
  touch  — stop = intrabar touch of the stop price (5m lows/highs)
  close  — stop = a 15m CLOSE beyond the stop (how the user actually trades)
Metrics per alert: stopped?, R at horizon, MFE in R (before stop).
Horizon: equities → that session's RTH close · crypto → +24h.
First fire per (session, symbol, type) only.
"""
import pandas as pd, numpy as np, warnings, json
warnings.filterwarnings("ignore")
import yfinance as yf

sent = pd.read_csv("alerts_sent.csv", low_memory=False)
sent["created_at"] = pd.to_datetime(sent["created_at"], utc=True, format="mixed")
sent = sent.sort_values("created_at").groupby(["session_date","symbol","alert_type"], as_index=False).first()
print("unique setups to grade:", len(sent))

symbols = sorted(sent["symbol"].unique())
data = {}
for i in range(0, len(symbols), 25):
    batch = symbols[i:i+25]
    try:
        d = yf.download(batch, start="2026-06-25", end="2026-07-04", interval="5m",
                        group_by="ticker", progress=False, prepost=False, threads=True)
        for s in batch:
            try:
                bars = d[s].dropna(subset=["Close"]) if len(batch) > 1 else d.dropna(subset=["Close"])
                if len(bars): data[s] = bars
            except Exception: pass
    except Exception as e:
        print("batch fail", batch[0], str(e)[:60])
print("symbols with bars:", len(data), "of", len(symbols))

rows = []
skip = {"no_bars":0, "bad_risk":0, "no_window":0}
for _, a in sent.iterrows():
    s, e, st = a["symbol"], a["entry"], a["stop"]
    if s not in data: skip["no_bars"] += 1; continue
    is_buy = str(a["direction"]) != "SHORT"
    risk = (e - st) if is_buy else (st - e)
    if not (risk > 0 and e > 0): skip["bad_risk"] += 1; continue
    bars = data[s]
    t0 = a["created_at"].tz_convert(bars.index.tz)
    crypto = "-USD" in s
    t1 = t0 + pd.Timedelta(hours=24) if crypto else t0.normalize() + pd.Timedelta(hours=16)
    w = bars[(bars.index >= t0) & (bars.index <= t1)]
    if len(w) < 2: skip["no_window"] += 1; continue
    hi, lo, cl = w["High"].values, w["Low"].values, w["Close"].values
    sgn = 1.0 if is_buy else -1.0
    # touch convention (5m wicks)
    hit = np.where((lo <= st) if is_buy else (hi >= st))[0]
    ti = hit[0] if len(hit) else None
    seg_hi = hi[:ti+1] if ti is not None else hi
    seg_lo = lo[:ti+1] if ti is not None else lo
    mfe_t = (max(seg_hi) - e)/risk if is_buy else (e - min(seg_lo))/risk
    r_t = -1.0 if ti is not None else sgn*(cl[-1] - e)/risk
    # close convention (15m closes)
    w15 = w["Close"].resample("15min").last().dropna()
    c15 = w15.values
    hitc = np.where((c15 < st) if is_buy else (c15 > st))[0]
    ci = hitc[0] if len(hitc) else None
    r_c = sgn*(c15[ci] - e)/risk if ci is not None else sgn*(cl[-1] - e)/risk
    rows.append(dict(symbol=s, alert_type=a["alert_type"].replace("tv_",""), session=a["session_date"],
                     direction="BUY" if is_buy else "SHORT", crypto=crypto,
                     stopped_touch=ti is not None, r_touch=round(r_t,3),
                     stopped_close=ci is not None, r_close=round(r_c,3), mfe=round(mfe_t,3)))

g = pd.DataFrame(rows)
g.to_csv("graded_week.csv", index=False)
print("graded:", len(g), "skips:", skip)

def agg(d):
    return pd.Series(dict(N=len(d),
        stopT=f"{d.stopped_touch.mean()*100:.0f}%", stopC=f"{d.stopped_close.mean()*100:.0f}%",
        avgR_T=round(d.r_touch.mean(),2), avgR_C=round(d.r_close.mean(),2),
        medMFE=round(d.mfe.median(),2)))
print("\n===== BY SETUP (N>=8) =====")
by = g.groupby("alert_type").apply(agg)
print(by[by.N >= 8].sort_values("avgR_C", ascending=False).to_string())
print("\n===== SMALL-N SETUPS (N<8) =====")
print(by[by.N < 8].sort_values("avgR_C", ascending=False).to_string())
print("\n===== ALL / equities vs crypto =====")
print(g.groupby("crypto").apply(agg).to_string())
print("\n===== TOP SYMBOLS (N>=8) =====")
bs = g.groupby("symbol").apply(agg)
print(bs[bs.N >= 8].sort_values("avgR_C", ascending=False).to_string())
# convention gap: shakeouts = touched stop but survived close-convention
sh = g[(g.stopped_touch) & (~g.stopped_close)]
print(f"\nSHAKEOUTS (wick hit stop, 15m close held): {len(sh)} of {g.stopped_touch.sum()} touch-stops "
      f"({len(sh)/max(1,g.stopped_touch.sum())*100:.0f}%) · their avg r_close: {sh.r_close.mean():.2f}R")
