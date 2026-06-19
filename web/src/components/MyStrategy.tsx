/** MyStrategy — Performance > Strategy Analysis (#64 Sub-spec I/K).
 *  EVERY live catalog pattern (from Settings) with a Learn link, your results overlaid where
 *  you've traded it. Doubles as the full pattern reference + your per-setup edge. Traded
 *  patterns sort to the top by avg R; untraded ones show the setup you can go learn.
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

const MIN_SAMPLE = 5;
const VERDICT: Record<string, { label: string; cls: string }> = {
  edge: { label: "EDGE", cls: "bg-bullish-subtle text-bullish-text" },
  cut: { label: "CUT", cls: "bg-bearish-subtle text-bearish-text" },
  building: { label: "BUILDING", cls: "bg-surface-3 text-text-faint" },
  ok: { label: "OK", cls: "bg-surface-3 text-text-muted" },
};

interface Stat { count: number; won: number; winPct: number; avgR: number | null; totalR: number; verdict: string }

export default function MyStrategy() {
  const nav = useNavigate();
  const { data: closed } = useClosedTrades();
  const { data: config } = useAlertConfig();

  // your closed trades grouped by pattern
  const byPattern = new Map<string, RealTrade[]>();
  for (const t of closed ?? []) {
    if (!t.alert_type) continue;
    if (!byPattern.has(t.alert_type)) byPattern.set(t.alert_type, []);
    byPattern.get(t.alert_type)!.push(t);
  }
  const statOf = (code: string): Stat | null => {
    const ts = byPattern.get(code);
    if (!ts || !ts.length) return null;
    const rs = ts.map(rOf).filter((r): r is number => r != null);
    const won = ts.filter((t) => (rOf(t) ?? t.pnl ?? 0) > 0).length;
    const totalR = rs.reduce((s, r) => s + r, 0);
    const avgR = rs.length ? totalR / rs.length : null;
    const verdict = ts.length < MIN_SAMPLE ? "building" : avgR != null && avgR >= 0.5 ? "edge" : avgR != null && avgR < 0 ? "cut" : "ok";
    return { count: ts.length, won, winPct: ts.length ? Math.round((won / ts.length) * 100) : 0, avgR, totalR, verdict };
  };

  // every catalog pattern + your stats overlay
  const rows = (config ?? [])
    .map((c) => ({ code: c.alert_type, label: c.label || formatSetup(c.alert_type), stat: statOf(c.alert_type) }))
    .sort((a, b) => {
      const at = a.stat ? 1 : 0, bt = b.stat ? 1 : 0;
      if (at !== bt) return bt - at;                                  // traded first
      if (a.stat && b.stat) return (b.stat.avgR ?? -Infinity) - (a.stat.avgR ?? -Infinity);
      return a.label.localeCompare(b.label);                          // untraded: A→Z
    });
  const edges = rows.filter((r) => r.stat?.verdict === "edge");
  const cuts = rows.filter((r) => r.stat?.verdict === "cut");

  if ((config ?? []).length === 0) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[13px] text-text-faint">Loading the pattern catalog…</div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-text-muted">
        Every setup we alert on — your win-rate and R fill in as you log trades. <span className="text-accent">Tap any pattern to learn the setup.</span>
      </p>

      <div className="rounded-xl border border-accent-muted bg-accent-subtle/40 p-3.5 text-[13px] text-text-secondary leading-relaxed">
        <span className="font-semibold text-text-primary">What to do — </span>
        {edges.length > 0
          ? <>lean into <span className="text-bullish-text font-medium">{edges.map((e) => e.label).join(", ")}</span> (your proven edge).</>
          : <>no proven edge yet — log trades, no setup has {MIN_SAMPLE}+ yet.</>}
        {cuts.length > 0 && <> Consider cutting <span className="text-bearish-text font-medium">{cuts.map((c) => c.label).join(", ")}</span>.</>}
      </div>

      <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
        <div className="flex items-center gap-3 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint border-b border-border-subtle">
          <span className="flex-1">Pattern · tap to learn</span>
          <span className="w-12 text-right">Win</span>
          <span className="w-16 text-right">Avg R</span>
          <span className="w-16 text-right">Total R</span>
        </div>
        {rows.map((r) => (
          <button key={r.code} onClick={() => nav(`/pattern/${encodeURIComponent(r.code)}`)} title="Learn this pattern"
            className="group w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-2/40 border-b border-border-subtle last:border-0 transition-colors">
            <span className="flex-1 min-w-0 flex items-center gap-2">
              <span className="text-[13px] font-semibold text-accent underline decoration-dotted decoration-text-faint/60 underline-offset-2 group-hover:decoration-accent truncate">{r.label}</span>
              {r.stat && <span className="text-[11px] text-text-faint shrink-0">{r.stat.won}/{r.stat.count}</span>}
              {r.stat && <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${VERDICT[r.stat.verdict].cls}`}>{VERDICT[r.stat.verdict].label}</span>}
            </span>
            {r.stat ? (
              <>
                <span className={`w-12 text-right font-mono text-[12px] tabular-nums ${r.stat.winPct >= 50 ? "text-bullish-text" : "text-bearish-text"}`}>{r.stat.winPct}%</span>
                <span className={`w-16 text-right font-mono text-[12px] tabular-nums ${(r.stat.avgR ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.stat.avgR != null ? `${r.stat.avgR >= 0 ? "+" : ""}${r.stat.avgR.toFixed(1)}R` : "—"}</span>
                <span className={`w-16 text-right font-mono text-[12px] font-semibold tabular-nums ${r.stat.totalR >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.stat.totalR >= 0 ? "+" : ""}{r.stat.totalR.toFixed(1)}R</span>
              </>
            ) : (
              <span className="text-[11px] text-text-faint italic shrink-0">no trades yet</span>
            )}
            <ChevronRight size={15} className="shrink-0 text-text-faint group-hover:text-accent transition-colors" />
          </button>
        ))}
      </div>

      <p className="text-[11px] text-text-faint"><span className="text-bullish-text">EDGE</span> = working · <span className="text-bearish-text">CUT</span> = losing · <span className="text-text-muted">BUILDING</span> = under {MIN_SAMPLE} trades. Traded setups sort first; the rest are the catalog you can learn. Feeds the AI weekly review.</p>
    </div>
  );
}
