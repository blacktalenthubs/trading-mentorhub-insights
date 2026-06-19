/** AlertCard — the redesigned hero alert card (Sub-spec J), wired to live alert data.
 *  Collapsible: a one-line row by default, expands to the full card on tap (keeps Today
 *  clean with many signals; fast EOD scanning). Carries the plain-English WHY (C), the
 *  real-level target (A), and the Took capture (I): "Took it" → form for YOUR actual
 *  entry + exit → POST /report → win/loss + R. Exit optional → log an OPEN position,
 *  add the exit later at EOD. Distinct from SignalCard (scanner results).
 */
import { useState } from "react";
import type { Alert } from "../types";
import { formatSetup } from "../lib/alertFormat";
import { useReportTrade } from "../api/hooks";
import { Info, LineChart, BookOpen, Check, ChevronRight, X } from "lucide-react";

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

export default function AlertCard({ a, onChart, onHide, defaultExpanded = false }: { a: Alert; onChart?: (symbol: string) => void; onHide?: (id: number) => void; defaultExpanded?: boolean }) {
  const dir = (a.direction || "").toUpperCase();
  const long = dir === "BUY" || dir === "LONG";
  const grade = (a.grade || "C").toUpperCase();
  const why = a.description || a.entry_guidance || formatSetup(a.alert_type);

  const report = useReportTrade();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [showForm, setShowForm] = useState(false);
  const [entryStr, setEntryStr] = useState(a.entry != null ? String(a.entry) : "");
  const [exitStr, setExitStr] = useState("");
  const [local, setLocal] = useState<{ exit_price: number | null; r_multiple: number | null } | null>(null);

  const took = a.user_action === "took" || local !== null;
  const exitPx = local ? local.exit_price : a.exit_price ?? null;
  const r = local ? local.r_multiple : a.r_multiple ?? null;
  const closed = took && exitPx != null;
  const open = took && exitPx == null;
  const potential =
    a.entry != null && a.target_1 != null && a.stop != null && a.entry !== a.stop
      ? Math.abs((a.target_1 - a.entry) / (a.entry - a.stop))
      : null;

  const submit = () => {
    const entry = parseFloat(entryStr);
    const exit = exitStr.trim() === "" ? null : parseFloat(exitStr);
    if (isNaN(entry) || (exit !== null && isNaN(exit))) return;
    report.mutate(
      { alertId: a.id, entry, exit },
      { onSuccess: (res) => { setLocal({ exit_price: res.exit_price, r_multiple: res.r_multiple }); setShowForm(false); } },
    );
  };

  // compact status shown in the collapsed row (and right-aligned)
  const statusBadge = closed
    ? <span className={`font-mono text-[11px] font-semibold tabular-nums ${(r ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r != null ? `${r >= 0 ? "+" : ""}${r.toFixed(1)}R` : "closed"}</span>
    : open
    ? <span className="text-[11px] font-medium text-warning-text">Open</span>
    : potential != null
    ? <span className="font-mono text-[11px] text-text-faint tabular-nums">→ {potential.toFixed(1)}R</span>
    : null;

  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 shadow-card">
      {/* header — always visible, toggles expand; × hides the signal */}
      <div className="flex w-full items-center px-3.5 py-3 rounded-xl hover:bg-surface-2/40 transition-colors">
        <button onClick={() => setExpanded((e) => !e)} className="flex flex-1 items-center gap-2 text-left min-w-0">
          <ChevronRight size={14} className={`shrink-0 text-text-faint transition-transform ${expanded ? "rotate-90" : ""}`} />
          <span className="font-display font-semibold text-text-primary">{a.symbol}</span>
          <span className={`text-[11px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
          <span className={`text-[11px] font-bold w-5 h-5 grid place-items-center rounded border ${GRADE_STYLE[grade] ?? GRADE_STYLE.C}`}>{grade}</span>
          <div className="ml-auto flex items-center gap-2 shrink-0 pl-2">
            <span className="hidden sm:inline text-[11px] text-text-faint max-w-[130px] truncate">{formatSetup(a.alert_type)}</span>
            <span className="text-[11px] text-text-faint tabular-nums">{timeAgo(a.created_at)}</span>
            {(!expanded || took) && statusBadge}
          </div>
        </button>
        {onHide && !took && (
          <button onClick={() => onHide(a.id)} title="Hide this signal" className="ml-1 p-1 text-text-faint hover:text-text-secondary shrink-0 transition-colors"><X size={13} /></button>
        )}
      </div>

      {expanded && (
        <div className="px-3.5 pb-3.5">
          {/* the WHY */}
          {why && <p className="text-[13px] leading-snug text-text-secondary">{why}</p>}

          {/* entry · target · stop (the plan) */}
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

          {/* capture form / result / action */}
          {showForm ? (
            <div className="mt-3 border-t border-border-subtle pt-3 space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-text-faint">Log your trade · {formatSetup(a.alert_type)}</div>
              <div className="flex gap-2">
                <label className="flex-1 text-[11px] text-text-muted">
                  Your entry
                  <input value={entryStr} onChange={(e) => setEntryStr(e.target.value)} inputMode="decimal"
                    className="mt-0.5 w-full rounded-md bg-surface-2 border border-border-default px-2 py-1 font-mono text-[12px] text-text-primary focus:border-accent outline-none" />
                </label>
                <label className="flex-1 text-[11px] text-text-muted">
                  Your exit <span className="text-text-faint normal-case">(blank = open)</span>
                  <input value={exitStr} onChange={(e) => setExitStr(e.target.value)} inputMode="decimal" autoFocus placeholder="leave blank if open"
                    className="mt-0.5 w-full rounded-md bg-surface-2 border border-border-default px-2 py-1 font-mono text-[12px] text-text-primary focus:border-accent outline-none" />
                </label>
              </div>
              <div className="flex gap-2">
                <button onClick={submit} disabled={report.isPending}
                  className="flex-1 text-[12px] font-semibold py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 transition-colors">
                  {report.isPending ? "Saving…" : "Save trade"}
                </button>
                <button onClick={() => setShowForm(false)} className="px-3 text-[12px] text-text-muted hover:text-text-secondary">Cancel</button>
              </div>
            </div>
          ) : closed ? (
            <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
              <span className="inline-flex items-center gap-1 text-[12px] font-medium text-bullish-text"><Check size={14} /> Took it</span>
              {r != null
                ? <span className={`font-mono text-[12px] font-semibold tabular-nums ${r >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r >= 0 ? "Win" : "Loss"} {r >= 0 ? "+" : ""}{r.toFixed(1)}R</span>
                : <span className="font-mono text-[12px] text-text-muted tabular-nums">Closed @ {exitPx != null ? px(exitPx) : "—"}</span>}
            </div>
          ) : open ? (
            <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
              <span className="inline-flex items-center gap-1 text-[12px] font-medium text-warning-text"><Check size={14} /> Took it · Open</span>
              <button onClick={() => { setExitStr(""); setShowForm(true); }} className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-surface-3 text-text-primary hover:bg-surface-4 transition-colors">Add exit</button>
            </div>
          ) : (
            <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-2.5">
              <button onClick={() => setShowForm(true)} className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors">Took it</button>
              {potential != null && <span className="font-mono text-[12px] tabular-nums font-semibold text-text-muted">→ {potential.toFixed(1)}R</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
