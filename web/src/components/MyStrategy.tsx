/** MyStrategy — Performance > Strategy Analysis (#64 Sub-spec I).
 *  YOUR per-pattern results from the trades you actually took: win-rate, avg R, total R.
 *  Answers "which of MY setups make money — trade more of what works, cut what bleeds."
 *  Built from your closed RealTrades (real entry/exit). Feeds the AI weekly review next.
 */
import { useNavigate } from "react-router-dom";
import { useClosedTrades, useAlertConfig } from "../api/hooks";
import type { RealTrade } from "../api/hooks";
import { formatSetup } from "../lib/alertFormat";
import { ChevronRight } from "lucide-react";

function isLong(t: RealTrade) {
  const d = (t.direction || "").toUpperCase();
  return d === "BUY" || d === "LONG";
}
function rOf(t: RealTrade): number | null {
  if (t.exit_price == null || t.stop_price == null || t.entry_price === t.stop_price) return null;
  const reward = isLong(t) ? t.exit_price - t.entry_price : t.entry_price - t.exit_price;
  return reward / Math.abs(t.entry_price - t.stop_price);
}

const MIN_SAMPLE = 5; // below this, per-pattern stats are noise — be honest
const VERDICT: Record<string, { label: string; cls: string }> = {
  edge: { label: "EDGE", cls: "bg-bullish-subtle text-bullish-text" },
  cut: { label: "CUT", cls: "bg-bearish-subtle text-bearish-text" },
  building: { label: "BUILDING", cls: "bg-surface-3 text-text-faint" },
  ok: { label: "OK", cls: "bg-surface-3 text-text-muted" },
};

export default function MyStrategy() {
  const nav = useNavigate();
  const { data: closed } = useClosedTrades();
  const { data: config } = useAlertConfig();
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
    const avgR = rs.length ? totalR / rs.length : null;
    const verdict =
      ts.length < MIN_SAMPLE ? "building"
      : avgR != null && avgR >= 0.5 ? "edge"
      : avgR != null && avgR < 0 ? "cut"
      : "ok";
    return { pattern, count: ts.length, won, winPct: ts.length ? Math.round((won / ts.length) * 100) : 0, avgR, totalR, verdict };
  }).sort((a, b) => {
    // reliable patterns (enough sample) first, so n=1 noise sinks to the bottom
    const ar = a.count >= MIN_SAMPLE ? 1 : 0, br = b.count >= MIN_SAMPLE ? 1 : 0;
    if (ar !== br) return br - ar;
    return (b.avgR ?? -Infinity) - (a.avgR ?? -Infinity);
  });
  // split live (in the canonical catalog / Settings) vs retired-legacy
  const activeCodes = new Set((config ?? []).map((c) => c.alert_type));
  const ready = config != null;
  const liveRows = ready ? rows.filter((r) => activeCodes.has(r.pattern)) : rows;
  const edges = liveRows.filter((r) => r.verdict === "edge");
  const cuts = liveRows.filter((r) => r.verdict === "cut");
  const buildingCount = liveRows.filter((r) => r.verdict === "building").length;

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
        Which of <span className="text-text-secondary">your</span> setups actually make money — from the trades you took. <span className="text-accent">Tap any pattern to learn the setup.</span>
      </p>
      <div className="rounded-xl border border-accent-muted bg-accent-subtle/40 p-3.5 text-[13px] text-text-secondary leading-relaxed">
        <span className="font-semibold text-text-primary">What to do — </span>
        {edges.length > 0
          ? <>lean into <span className="text-bullish-text font-medium">{edges.map((e) => formatSetup(e.pattern)).join(", ")}</span> (your proven edge so far).</>
          : <>no proven edge yet — keep logging trades, no setup has {MIN_SAMPLE}+ trades.</>}
        {cuts.length > 0 && <> Consider cutting <span className="text-bearish-text font-medium">{cuts.map((c) => formatSetup(c.pattern)).join(", ")}</span>.</>}
        {buildingCount > 0 && <span className="text-text-faint"> {buildingCount} pattern{buildingCount > 1 ? "s" : ""} still building a sample — ignore until they have {MIN_SAMPLE}+ trades.</span>}
      </div>
      <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
        <div className="flex items-center gap-4 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint border-b border-border-subtle">
          <span className="flex-1">Pattern</span>
          <span className="w-12 text-right">Win</span>
          <span className="w-16 text-right">Avg R</span>
          <span className="w-16 text-right">Total R</span>
        </div>
        {liveRows.map((r) => (
          <button key={r.pattern} onClick={() => nav(`/pattern/${encodeURIComponent(r.pattern)}`)} title="Learn this pattern"
            className="group w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-2/40 border-b border-border-subtle last:border-0 transition-colors">
            <span className="flex-1 min-w-0 flex items-center gap-2">
              <span className="text-[13px] font-semibold text-accent underline decoration-dotted decoration-text-faint/60 underline-offset-2 group-hover:decoration-accent truncate">{formatSetup(r.pattern)}</span>
              <span className="text-[11px] text-text-faint shrink-0">{r.won}/{r.count}</span>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${VERDICT[r.verdict].cls}`}>{VERDICT[r.verdict].label}</span>
            </span>
            <span className={`w-12 text-right font-mono text-[12px] tabular-nums ${r.winPct >= 50 ? "text-bullish-text" : "text-bearish-text"}`}>{r.winPct}%</span>
            <span className={`w-16 text-right font-mono text-[12px] tabular-nums ${(r.avgR ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.avgR != null ? `${r.avgR >= 0 ? "+" : ""}${r.avgR.toFixed(1)}R` : "—"}</span>
            <span className={`w-16 text-right font-mono text-[12px] font-semibold tabular-nums ${r.totalR >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.totalR >= 0 ? "+" : ""}{r.totalR.toFixed(1)}R</span>
            <ChevronRight size={15} className="shrink-0 text-text-faint group-hover:text-accent transition-colors" />
          </button>
        ))}
      </div>
      <p className="text-[11px] text-text-faint"><span className="text-bullish-text">EDGE</span> = working · <span className="text-bearish-text">CUT</span> = losing · <span className="text-text-muted">BUILDING</span> = under {MIN_SAMPLE} trades, not yet reliable. Per-pattern stats only mean something with sample size — keep logging. This feeds the AI weekly review.</p>
    </div>
  );
}
