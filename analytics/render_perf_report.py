#!/usr/bin/env python3
"""Render a performance_report.json into the Performance-page HTML (real data, mock layout)."""
import json, sys, statistics as st
from collections import defaultdict, OrderedDict

def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else 0.0

def render(path_json, path_html, period_label):
    S = json.load(open(path_json))
    closed = [s for s in S if not s.get("open")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    wr = round(wins * 100 / len(closed)) if closed else 0

    # leaderboard by pattern (closed only)
    byp = defaultdict(list)
    for s in closed:
        byp[s["pattern"]].append(s)
    lb = []
    for pat, items in byp.items():
        w = sum(1 for i in items if i["result"] == "WIN")
        ae = sum(1 for i in items if i.get("above_entry"))
        lb.append(dict(pat=pat, style=items[0]["style"], n=len(items),
                       wr=round(w * 100 / len(items)),
                       ae=round(ae * 100 / len(items)),
                       mfe=med([i["mfe_pct"] for i in items]),
                       mae=med([i["mae_pct"] for i in items])))
    lb = [r for r in lb if r["n"] >= 3]          # drop tiny samples
    lb.sort(key=lambda x: (-x["wr"], -x["n"]))

    def wcls(v): return "up" if v >= 60 else ("amb" if v >= 50 else "dn")
    def fillcol(v): return "var(--grn)" if v >= 60 else ("var(--amb)" if v >= 50 else "var(--red)")
    lbrows = ""
    for i, r in enumerate(lb, 1):
        tag = {"Day": "day", "Swing": "swing", "Long": "long"}.get(r["style"], "day")
        tt = {"Day": "DAY", "Swing": "SW", "Long": "LT"}[r["style"]]
        lbrows += f"""<tr><td class="rk">{i}</td><td class="pat"><div class="nm">{r['pat']}</div></td>
          <td><div class="winbar"><div class="tk"><div class="fl" style="width:{max(4,r['wr'])}%;background:{fillcol(r['wr'])}"></div></div><span class="pc {wcls(r['wr'])}">{r['wr']}%</span></div></td>
          <td class="mono mut">{r['ae']}%</td>
          <td class="mono up">{r['mfe']:+.1f}%</td><td class="mono dn">{r['mae']:+.1f}%</td>
          <td class="mono">{r['n']} <span class="tag {tag}">{tt}</span></td></tr>"""

    # grouped by date
    byd = OrderedDict()
    for s in sorted(S, key=lambda x: (x["session_date"], x["alert_et"] or "")):
        byd.setdefault(s["session_date"], []).append(s)
    ddrows = ""
    for d, items in sorted(byd.items(), reverse=True)[:4]:   # last 4 sessions in the table
        cl = [i for i in items if not i.get("open")]
        dw = sum(1 for i in cl if i["result"] == "WIN")
        dwr = round(dw * 100 / len(cl)) if cl else 0
        dmfe = med([i["mfe_pct"] for i in items])
        ddrows += f"""<tr class="grp"><td colspan="10">▾ {d} <span class="meta"><span class="wr">{dwr}% win</span> · {len(items)} alerts · median MFE {dmfe:+.1f}%</span></td></tr>"""
        for i in items:
            win = i["result"] == "WIN"
            res = "✅ WIN" if win else f"🛑 LOSS {i['realized_stop_pct']:+.1f}%" if i.get("realized_stop_pct") is not None else "🛑 LOSS"
            op = ' · <span style="color:var(--blu)">open</span>' if i.get("open") else ""
            hi_c = "up" if i["mfe_pct"] > 0 else ""
            lo_c = "dn" if i["mae_pct"] < -0.5 else ""
            ddrows += f"""<tr><td class="sym">{i['symbol']}</td><td class="typ">{i['pattern']}</td>
              <td class="mono">{i['entry']:.2f}</td><td class="mono">{i['stop']:.2f}</td>
              <td class="mono {hi_c}">{i['intraday_high']:.2f}</td><td class="mono {lo_c}">{i['intraday_low']:.2f}</td>
              <td class="mono">{i['eod_close']:.2f}</td><td class="mono up">{i['mfe_pct']:+.1f}%</td>
              <td class="mono dn">{i['max_dd_pct']:+.1f}%</td>
              <td class="res {'w' if win else 's'}">{res}{op}</td></tr>"""

    html = TEMPLATE.format(period=period_label, n=len(S), npat=len(lb), wr=wr,
                           mfe=med([s["mfe_pct"] for s in closed]), mae=med([s["mae_pct"] for s in closed]),
                           lbrows=lbrows, ddrows=ddrows)
    open(path_html, "w").write(html)
    print(f"wrote {path_html} — {len(S)} alerts, {wr}% win ({len(closed)} closed)")

TEMPLATE = """<style>
:root{{--bg:#0a0d12;--panel:#111722;--panel2:#0d131c;--line:#1e2733;--line2:#28323f;--txt:#e8edf3;--mut:#8b97a6;--dim:#5b6675;--grn:#3fb950;--red:#f85149;--amb:#e0a533;--blu:#58a6ff;--mono:ui-monospace,"SF Mono",Menlo,monospace;--sans:-apple-system,"Segoe UI",Roboto,sans-serif}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{background:var(--bg);color:var(--txt);font-family:var(--sans);font-size:14px}}.mono{{font-family:var(--mono);font-variant-numeric:tabular-nums}}.wrap{{max-width:1200px;margin:0 auto;padding:20px 20px 60px}}.up{{color:var(--grn)}}.dn{{color:var(--red)}}.amb{{color:var(--amb)}}.mut{{color:var(--mut)}}
.top{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding-bottom:14px;border-bottom:1px solid var(--line)}}.top h1{{font-family:var(--mono);font-size:15px;letter-spacing:.22em;color:var(--amb);font-weight:600;text-transform:uppercase}}.top .sub{{color:var(--dim);font-size:12px;margin-top:3px}}
.strip{{display:flex;gap:26px;flex-wrap:wrap;margin-top:14px;padding:12px 16px;background:var(--panel2);border:1px solid var(--line);border-radius:9px}}.strip .m{{display:flex;flex-direction:column}}.strip .m .v{{font-family:var(--mono);font-size:17px;font-weight:650}}.strip .m .l{{color:var(--dim);font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:1px}}
.sect{{font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--amb);margin:26px 0 6px;display:flex;align-items:center;gap:10px}}.sect::after{{content:"";flex:1;height:1px;background:var(--line)}}.sect .n{{color:var(--dim);letter-spacing:.02em;text-transform:none;font-size:11px}}.hint{{color:var(--dim);font-size:11.5px;margin:0 0 12px}}
.lb{{background:var(--panel);border:1px solid var(--line2);border-radius:12px;overflow:hidden}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}.lb table{{min-width:640px}}.lb th{{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:600;padding:11px 14px;text-align:right;border-bottom:1px solid var(--line2)}}.lb td{{padding:12px 14px;text-align:right;border-bottom:1px solid var(--line)}}.lb tr:last-child td{{border-bottom:0}}.lb tr:hover td{{background:rgba(255,255,255,.025)}}.rk{{color:var(--dim);font-family:var(--mono);text-align:center;width:34px}}.pat{{text-align:left}}.pat .nm{{font-weight:650;color:#fff;font-size:13.5px}}.winbar{{display:flex;align-items:center;gap:9px;justify-content:flex-end}}.winbar .tk{{width:120px;height:9px;background:var(--panel2);border-radius:5px;overflow:hidden}}.winbar .fl{{height:100%;border-radius:5px}}.winbar .pc{{font-family:var(--mono);font-size:13.5px;font-weight:650;width:40px;text-align:right}}.tag{{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 6px;border-radius:4px}}.tag.day{{background:rgba(88,166,255,.12);color:var(--blu)}}.tag.swing{{background:rgba(224,165,51,.12);color:var(--amb)}}.tag.long{{background:rgba(63,185,80,.12);color:var(--grn)}}
.tblwrap{{background:var(--panel);border:1px solid var(--line);border-radius:11px;overflow:hidden}}.tblwrap table{{min-width:820px}}.tblwrap th{{color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:600;padding:9px 13px;text-align:right;border-bottom:1px solid var(--line)}}.tblwrap td{{padding:8px 13px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}}.tblwrap tr:hover td{{background:rgba(255,255,255,.02)}}td.sym{{text-align:left;font-weight:700;color:#fff;font-family:var(--mono)}}td.typ{{text-align:left;color:var(--mut);font-size:11px;font-family:var(--mono)}}.res{{font-family:var(--mono);font-size:11px;font-weight:600}}.res.w{{color:var(--grn)}}.res.s{{color:var(--red)}}tr.grp td{{background:var(--panel2);color:var(--txt);font-family:var(--mono);font-size:12px;font-weight:650;text-align:left;padding:9px 14px;border-top:1px solid var(--line2)}}tr.grp td .meta{{color:var(--dim);font-weight:400;margin-left:12px;font-size:11px}}tr.grp td .wr{{color:var(--grn);font-weight:600}}
.foot-note{{color:var(--dim);font-size:11px;margin-top:22px;line-height:1.6;font-family:var(--mono)}}
</style>
<div class="wrap">
  <div class="top"><div><h1>Performance</h1><div class="sub">Which entry patterns work — every delivered alert scored against price at EOD. Win = target before stop.</div></div></div>
  <div class="strip">
    <div class="m"><span class="v mono">{n}</span><span class="l">alerts scored</span></div>
    <div class="m"><span class="v mono">{npat}</span><span class="l">entry patterns</span></div>
    <div class="m"><span class="v mono up">{wr}%</span><span class="l">win (closed)</span></div>
    <div class="m"><span class="v mono up">{mfe:+.1f}%</span><span class="l">median MFE</span></div>
    <div class="m"><span class="v mono dn">{mae:+.1f}%</span><span class="l">median MAE</span></div>
  </div>
  <div class="sect">Entry patterns, ranked <span class="n">· by win rate · stop is the judge</span></div>
  <p class="hint">Win = target hit before stop (or closed green, no stop) — the strict, stop-is-judge read. "Above entry" = the lenient read (did intraday high clear entry at all). Big gap between them = the pattern pokes green then gets stopped (tight stops). Sorted by win rate; n≥3 only.</p>
  <div class="lb"><div class="scroll"><table><thead><tr><th class="rk">#</th><th class="pat" style="text-align:left">Entry pattern</th><th>Win rate</th><th>Above entry</th><th>Med MFE</th><th>Med MAE</th><th>Alerts</th></tr></thead><tbody>{lbrows}</tbody></table></div></div>
  <div class="sect">Alerts, grouped by date <span class="n">· {period}</span></div>
  <div class="tblwrap"><div class="scroll"><table><thead><tr><th>Sym</th><th>Setup</th><th>Entry</th><th>Stop</th><th>Intra hi</th><th>Intra lo</th><th>EOD</th><th>MFE</th><th>Max DD</th><th>Result</th></tr></thead><tbody>{ddrows}</tbody></table></div></div>
  <div class="foot-note">Real data · each delivered long alert replayed: intraday 5m (day) / daily (swing, 10-day window) from yfinance. Win = target before stop, else closed green. MFE/MAE/MaxDD from entry. Delivered-only — suppressed alerts excluded (so dedup'd winners aren't yet counted; #620 fixes that going forward).</div>
</div>"""

if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
