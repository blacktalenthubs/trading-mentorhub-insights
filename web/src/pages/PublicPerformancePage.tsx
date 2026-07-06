/** Public, read-only shared Performance snapshot — no auth, no app shell.
 *  Rendered at /public/performance/:token from a link the user created via the Share button.
 *  Reuses the aggregation helpers from RealTradesPage so the numbers match exactly.
 */
import { Fragment } from "react";
import { useParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { usePublicPerformance } from "../api/hooks";
import { median, pct, fmtDay, wrColor, aggregate, groupByDate } from "./RealTradesPage";

const STYLE_TAG: Record<string, string> = { Day: "text-sky-400", Swing: "text-amber-400", Long: "text-bullish-text" };

export default function PublicPerformancePage() {
  const { token } = useParams<{ token: string }>();
  const { data, isLoading, error } = usePublicPerformance(token ?? "");
  const alerts = data?.alerts ?? [];
  const closed = alerts.filter((a) => !a.open);
  const wins = closed.filter((a) => a.result === "WIN").length;
  const overallWr = closed.length ? Math.round((wins * 100) / closed.length) : 0;
  const lb = aggregate(alerts);
  const groups = groupByDate(alerts).slice(0, 3);
  const medMfe = median(alerts.map((a) => a.mfe_pct));

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      <div className="mx-auto max-w-5xl space-y-5 px-4 py-8">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle pb-4">
          <div>
            <h1 className="font-mono text-sm font-semibold uppercase tracking-[0.2em] text-amber-400">Performance · Shared{data?.period_label ? <span className="ml-2 normal-case tracking-normal text-text-primary">· {data.period_label}</span> : null}</h1>
            <p className="mt-1 text-xs text-text-faint">Which entry patterns actually work — every delivered alert scored against price. Read-only snapshot{data?.period_label ? ` of ${data.period_label}` : ""}{data?.shared_at ? ` · shared ${data.shared_at.slice(0, 10)}` : ""}.</p>
          </div>
          <a href="/" className="text-xs text-sky-400 hover:underline">BusyTradersDesk →</a>
        </div>

        {isLoading && <div className="flex items-center justify-center gap-2 py-16 text-sm text-text-muted"><Loader2 className="h-4 w-4 animate-spin" /> Loading…</div>}
        {error && <div className="rounded-lg bg-bearish-subtle p-4 text-center text-sm text-bearish-text">This shared report link is invalid or has expired.</div>}
        {!isLoading && !error && !alerts.length && <div className="rounded-lg border border-border-subtle bg-surface-2 p-6 text-center text-sm text-text-muted">No scored alerts in this snapshot.</div>}

        {!isLoading && !error && !!alerts.length && (
          <>
            <div className="flex flex-wrap gap-6 rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
              {[
                { v: `${alerts.length}`, l: "alerts scored" },
                { v: `${lb.length}`, l: "entry patterns" },
                { v: `${overallWr}%`, l: "win (closed)" },
                { v: pct(medMfe), l: "median peak" },
              ].map((m) => (
                <div key={m.l} className="flex flex-col">
                  <span className="font-mono text-lg font-semibold">{m.v}</span>
                  <span className="mt-0.5 text-[10px] uppercase tracking-wide text-text-faint">{m.l}</span>
                </div>
              ))}
            </div>

            <div>
              <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-amber-400">Entry patterns, ranked</div>
              <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-2">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-sm">
                    <thead><tr className="text-[10px] uppercase tracking-wide text-text-faint"><th className="px-3 py-2.5 text-center">#</th><th className="px-3 py-2.5 text-left">Pattern</th><th className="px-3 py-2.5 text-right">Win rate</th><th className="px-3 py-2.5 text-right">Med peak</th><th className="px-3 py-2.5 text-right">Alerts</th></tr></thead>
                    <tbody>
                      {lb.map((r, i) => (
                        <tr key={r.pattern} className="border-t border-border-subtle">
                          <td className="px-3 py-3 text-center font-mono text-text-faint">{i + 1}</td>
                          <td className="px-3 py-3 font-semibold">{r.pattern}</td>
                          <td className="px-3 py-3 text-right"><span className="font-mono font-semibold" style={{ color: wrColor(r.wr) }}>{r.wr}%</span></td>
                          <td className="px-3 py-3 text-right font-mono text-bullish-text">{pct(r.mfe)}</td>
                          <td className="px-3 py-3 text-right font-mono text-text-muted">{r.n} <span className={`text-[10px] ${STYLE_TAG[r.style] ?? "text-text-faint"}`}>{r.style === "Day" ? "DAY" : r.style === "Swing" ? "SW" : "LT"}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div>
              <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.14em] text-amber-400">Recent alerts</div>
              <p className="mb-2 text-[10.5px] leading-snug text-text-faint">Each alert is scored only on price <b className="text-text-muted">after it fired</b> — the small time under <b className="text-text-muted">Entry</b> is when it fired, under <b className="text-text-muted">Hi</b> is when the high printed. A move that happened before entry never counts.</p>
              <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-2">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm">
                    <thead><tr className="text-[10px] uppercase tracking-wide text-text-faint"><th className="px-3 py-2.5 text-left">Sym</th><th className="px-3 py-2.5 text-left">Setup</th><th className="px-3 py-2.5 text-right">Entry</th><th className="px-3 py-2.5 text-right">Hi</th><th className="px-3 py-2.5 text-right">EOD</th><th className="px-3 py-2.5 text-right">Peak</th><th className="px-3 py-2.5 text-right">Result</th></tr></thead>
                    <tbody>
                      {groups.map((g) => (
                        <Fragment key={g.date}>
                          <tr className="bg-surface-0"><td colSpan={7} className="border-t border-border-subtle px-3 py-2 font-mono text-xs font-semibold">{fmtDay(g.date)} <span className="ml-2 font-normal text-text-faint"><span className="text-bullish-text">{g.wr}% win</span> · {g.items.length} alerts</span></td></tr>
                          {g.items.map((a, i) => (
                            <tr key={`${a.symbol}-${i}`} className="border-t border-border-subtle font-mono">
                              <td className="px-3 py-2 text-left font-bold">{a.symbol}</td>
                              <td className="px-3 py-2 text-left font-sans text-[11px] text-text-muted">{a.pattern}</td>
                              <td className="px-3 py-2 text-right">{a.entry.toFixed(2)}{a.alert_et && <span className="block text-[9px] font-normal text-text-faint">{a.alert_et}</span>}</td>
                              <td className="px-3 py-2 text-right text-bullish-text">{a.intraday_high.toFixed(2)}{a.hi_et && <span className="block text-[9px] font-normal text-text-faint">@ {a.hi_et}</span>}</td>
                              <td className="px-3 py-2 text-right">{a.eod_close.toFixed(2)}{a.eod_et && <span className="block text-[9px] font-normal text-text-faint">{a.eod_et}</span>}</td>
                              <td className="px-3 py-2 text-right text-bullish-text">{pct(a.mfe_pct)}</td>
                              <td className={`px-3 py-2 text-right text-[11px] font-semibold ${a.result === "WIN" ? "text-bullish-text" : "text-bearish-text"}`}>{a.open ? "· open" : a.result === "WIN" ? "✓ WIN" : "✗ LOSS"}</td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <p className="pt-4 text-center text-[10px] text-text-faint">Educational only — not financial advice. Scored against price; assumes disciplined exits.</p>
          </>
        )}
      </div>
    </div>
  );
}
