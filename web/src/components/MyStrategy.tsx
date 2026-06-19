/** MyStrategy — Performance > Strategy Analysis (#64 Sub-spec I).
 *  YOUR per-pattern results from the trades you actually took: win-rate, avg R, total R.
 *  Answers "which of MY setups make money — trade more of what works, cut what bleeds."
 *  Built from your closed RealTrades (real entry/exit). Feeds the AI weekly review next.
 */
import { useNavigate } from "react-router-dom";
import { useClosedTrades } from "../api/hooks";
import type { RealTrade } from "../api/hooks";
import { formatSetup } from "../lib/alertFormat";

function isLong(t: RealTrade) {
  const d = (t.direction || "").toUpperCase();
  return d === "BUY" || d === "LONG";
}
function rOf(t: RealTrade): number | null {
  if (t.exit_price == null || t.stop_price == null || t.entry_price === t.stop_price) return null;
  const reward = isLong(t) ? t.exit_price - t.entry_price : t.entry_price - t.exit_price;
  return reward / Math.abs(t.entry_price - t.stop_price);
}

export default function MyStrategy() {
  const nav = useNavigate();
  const { data: closed } = useClosedTrades();
  const trades = (closed ?? []).filter((t) => t.alert_type);

  const map = new Map<string, RealTrade[]>();
  for (const t of trades) {
    const k = t.alert_type as string;
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(t);
  }
  const rows = [...map.entries()].map(([pattern, ts]) => {
    const rs = ts.map(rOf).filter((r): r is number => r != null);
    const won = ts.filter((t) => (rOf(t) ?? t.pnl ?? 0) > 0).length;
    const totalR = rs.reduce((s, r) => s + r, 0);
    return {
      pattern,
      count: ts.length,
      won,
      winPct: ts.length ? Math.round((won / ts.length) * 100) : 0,
      avgR: rs.length ? totalR / rs.length : null,
      totalR,
    };
  }).sort((a, b) => (b.avgR ?? -Infinity) - (a.avgR ?? -Infinity));

  if (trades.length === 0) {
    return (
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[13px] text-text-faint">
        No closed trades yet. Log trades in <span className="text-text-secondary">Today's EOD</span> (Took it → enter your exit) and your per-pattern edge builds up here.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-text-muted">
        Which of <span className="text-text-secondary">your</span> setups actually make money — from the trades you took. Trade more of what works; cut what bleeds.
      </p>
      <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
        <div className="flex items-center gap-4 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint border-b border-border-subtle">
          <span className="flex-1">Pattern</span>
          <span className="w-12 text-right">Win</span>
          <span className="w-16 text-right">Avg R</span>
          <span className="w-16 text-right">Total R</span>
        </div>
        {rows.map((r) => (
          <button key={r.pattern} onClick={() => nav("/learn")} title="Learn this pattern"
            className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-surface-2/40 border-b border-border-subtle last:border-0 transition-colors">
            <span className="flex-1 min-w-0">
              <span className="text-[13px] font-semibold text-text-primary">{formatSetup(r.pattern)}</span>
              <span className="text-[11px] text-text-faint ml-2">{r.won}/{r.count} won</span>
            </span>
            <span className={`w-12 text-right font-mono text-[12px] tabular-nums ${r.winPct >= 50 ? "text-bullish-text" : "text-bearish-text"}`}>{r.winPct}%</span>
            <span className={`w-16 text-right font-mono text-[12px] tabular-nums ${(r.avgR ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.avgR != null ? `${r.avgR >= 0 ? "+" : ""}${r.avgR.toFixed(1)}R` : "—"}</span>
            <span className={`w-16 text-right font-mono text-[12px] font-semibold tabular-nums ${r.totalR >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.totalR >= 0 ? "+" : ""}{r.totalR.toFixed(1)}R</span>
          </button>
        ))}
      </div>
      <p className="text-[11px] text-text-faint">Sorted by your average R. This is what the AI weekly review will read to recommend which patterns to lean into.</p>
    </div>
  );
}
