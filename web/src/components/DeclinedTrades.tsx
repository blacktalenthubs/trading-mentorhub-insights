/** DeclinedTrades — Performance > Declined (#64 Sub-spec I).
 *  Signals you passed on (user_action="skipped"), organized for REVIEW, not a data dump:
 *  a top insight strip (what you pass on most) + collapsible day groups (newest open) with
 *  scannable rows showing the setup quality (R:R), not raw price noise. The "would it have
 *  worked?" ✓/✗ verdict (hit target before stop) is the next step — needs a price backfill.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAlertsHistory } from "../api/hooks";
import { formatSetup } from "../lib/alertFormat";
import { ChevronRight } from "lucide-react";
import type { Alert } from "../types";

const todayStr = () => new Date().toISOString().slice(0, 10);
function dayLabel(d: string): string {
  if (d === todayStr()) return "Today";
  const y = new Date(); y.setDate(y.getDate() - 1);
  if (d === y.toISOString().slice(0, 10)) return "Yesterday";
  const dt = new Date(d + "T00:00:00");
  return isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}
function timeStr(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).replace(" ", "").replace("AM", "a").replace("PM", "p");
}
function isLong(a: Alert) { const x = (a.direction || "").toUpperCase(); return x === "BUY" || x === "LONG"; }
function rr(a: Alert): number | null {
  if (a.entry == null || a.target_1 == null || a.stop == null || a.entry === a.stop) return null;
  return Math.abs((a.target_1 - a.entry) / (a.entry - a.stop));
}

function DeclinedRow({ a }: { a: Alert }) {
  const nav = useNavigate();
  const long = isLong(a);
  const r = rr(a);
  return (
    <div className="flex items-center gap-2.5 px-4 py-2.5 border-b border-border-subtle/50 last:border-0 hover:bg-surface-2/30 transition-colors">
      <span className="font-display text-[13px] font-semibold text-text-primary w-16 sm:w-20 shrink-0 truncate">{a.symbol}</span>
      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded shrink-0 ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
      {a.alert_type
        ? <button onClick={() => nav(`/pattern/${encodeURIComponent(a.alert_type)}`)} title="Learn this pattern" className="text-[11px] text-accent hover:underline truncate text-left flex-1 min-w-0">{formatSetup(a.alert_type)}</button>
        : <span className="flex-1" />}
      <span className={`font-mono text-[11px] tabular-nums shrink-0 ${r != null && r >= 2 ? "text-bullish-text" : "text-text-muted"}`}>{r != null ? `→ ${r.toFixed(1)}R` : "—"}</span>
      <span className="text-[11px] text-text-faint tabular-nums shrink-0 w-12 text-right">{timeStr(a.created_at)}</span>
    </div>
  );
}

function DayGroup({ day, items, defaultOpen }: { day: string; items: Alert[]; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center gap-2 px-4 py-2.5 hover:bg-surface-2/40 transition-colors">
        <ChevronRight size={13} className={`text-text-faint transition-transform ${open ? "rotate-90" : ""}`} />
        <span className="text-[12px] font-semibold text-text-primary">{dayLabel(day)}</span>
        <span className="ml-auto text-[11px] text-text-faint">{items.length} declined</span>
      </button>
      {open && <div className="border-t border-border-subtle">{items.map((a) => <DeclinedRow key={a.id} a={a} />)}</div>}
    </div>
  );
}

export default function DeclinedTrades() {
  const { data: alerts } = useAlertsHistory(30);
  const declined = (alerts ?? []).filter((a) => a.user_action === "skipped");

  const byDay = new Map<string, Alert[]>();
  for (const a of declined) {
    const day = a.session_date || (a.created_at || "").slice(0, 10);
    if (!day) continue;
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day)!.push(a);
  }
  const days = [...byDay.entries()].sort((a, b) => b[0].localeCompare(a[0]));
  for (const [, items] of days) items.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));

  const patCount = new Map<string, number>();
  for (const a of declined) if (a.alert_type) patCount.set(a.alert_type, (patCount.get(a.alert_type) || 0) + 1);
  const topPats = [...patCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-text-muted">
        Signals you <span className="text-text-secondary">passed on</span> — logged for review. <span className="text-text-faint">Coming: a ✓/✗ "would it have worked" badge (did it hit target before stop) so you can see if your filtering is sharp.</span>
      </p>

      {/* summary + insight strip */}
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-xl border border-border-subtle bg-surface-1 px-4 py-3.5">
        <div className="shrink-0">
          <div className="text-[10px] text-text-faint uppercase tracking-wider">Declined · 30 days</div>
          <div className="text-2xl font-mono font-bold text-text-primary">{declined.length}</div>
        </div>
        {topPats.length > 0 && (
          <div className="min-w-0">
            <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1.5">Most passed on</div>
            <div className="flex flex-wrap gap-1.5">
              {topPats.map(([code, n]) => (
                <span key={code} className="text-[11px] bg-surface-2 rounded-md px-2 py-0.5 text-text-secondary">{formatSetup(code)} <span className="text-text-faint">×{n}</span></span>
              ))}
            </div>
          </div>
        )}
      </div>

      {days.length > 0 ? (
        <div className="space-y-2">
          {days.map(([day, items], i) => <DayGroup key={day} day={day} items={items} defaultOpen={i === 0} />)}
        </div>
      ) : (
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[13px] text-text-faint">
          No declined signals yet. Tap <span className="text-text-secondary">Decline</span> on a Today signal to start tracking what you passed on.
        </div>
      )}
    </div>
  );
}
