/** AlertCard — the redesigned hero alert card (Sub-spec J), wired to live alert data.
 *  Carries the plain-English WHY (C), the real-level target (A), and the Took capture (I).
 *  Distinct from SignalCard (which renders scanner SignalResults). On-system; mobile-first.
 */
import type { Alert } from "../types";
import { formatSetup } from "../lib/alertFormat";
import { Info, LineChart, BookOpen, Check } from "lucide-react";

const px = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function timeAgo(iso?: string): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

const GRADE_STYLE: Record<string, string> = {
  A: "bg-bullish-subtle text-bullish-text border-bullish-muted",
  B: "bg-warning-subtle text-warning-text border-warning-muted",
  C: "bg-surface-3 text-text-muted border-border-default",
};

export default function AlertCard({ a, onChart }: { a: Alert; onChart?: (symbol: string) => void }) {
  const dir = (a.direction || "").toUpperCase();
  const long = dir === "BUY" || dir === "LONG";
  const grade = (a.grade || "C").toUpperCase();
  const took = a.user_action === "took";
  const why = a.description || a.entry_guidance || formatSetup(a.alert_type);
  const rr =
    a.entry != null && a.target_1 != null && a.stop != null && a.entry !== a.stop
      ? Math.abs((a.target_1 - a.entry) / (a.entry - a.stop))
      : null;

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5 shadow-card">
      {/* header */}
      <div className="flex items-center gap-2">
        <span className="font-display font-semibold text-text-primary">{a.symbol}</span>
        <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
        <span className={`text-[11px] font-bold w-5 h-5 grid place-items-center rounded border ${GRADE_STYLE[grade] ?? GRADE_STYLE.C}`}>{grade}</span>
        <span className="ml-auto text-[11px] text-text-faint truncate max-w-[40%]">{formatSetup(a.alert_type)}</span>
        <span className="text-[11px] text-text-faint tabular-nums">{timeAgo(a.created_at)}</span>
      </div>

      {/* the WHY */}
      {why && <p className="mt-2 text-[13px] leading-snug text-text-secondary line-clamp-2">{why}</p>}

      {/* entry · target · stop */}
      {(a.entry != null || a.target_1 != null || a.stop != null) && (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[12px] tabular-nums">
          {a.entry != null && <span className="text-text-muted">Entry <span className="text-text-primary">{px(a.entry)}</span></span>}
          {a.target_1 != null && <span className={long ? "text-bullish-text" : "text-bearish-text"}>Target {px(a.target_1)}</span>}
          {a.stop != null && <span className="text-text-muted">Stop <span className="text-bearish-text">{px(a.stop)}</span></span>}
        </div>
      )}

      {/* progressive disclosure */}
      <div className="mt-2.5 flex items-center gap-3 text-[11px] text-text-muted">
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><Info size={12} /> Why grade {grade}</button>
        <button onClick={() => onChart?.(a.symbol)} className="inline-flex items-center gap-1 hover:text-text-secondary"><LineChart size={12} /> Chart</button>
        <button className="inline-flex items-center gap-1 hover:text-text-secondary"><BookOpen size={12} /> Learn</button>
      </div>

      {/* action + R */}
      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
        {took
          ? <span className="inline-flex items-center gap-1 text-[12px] font-medium text-bullish-text"><Check size={14} /> Took it</span>
          : <button className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors">Took it</button>}
        {rr != null && <span className="font-mono text-[12px] tabular-nums font-semibold text-text-muted">→ {rr.toFixed(1)}R</span>}
      </div>
    </div>
  );
}
