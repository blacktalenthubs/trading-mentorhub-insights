/** DeclinedTrades — Performance > Declined (#64 Sub-spec I).
 *  Signals you passed on (user_action="skipped") — logged for later review: would taking it
 *  have worked? (the hit-target-before-stop outcome is a follow-up needing price backfill.)
 *  Today is the "what you declined" record; the verdict overlay comes next.
 */
import { useNavigate } from "react-router-dom";
import { useAlertsHistory } from "../api/hooks";
import { formatSetup } from "../lib/alertFormat";

const px = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function when(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export default function DeclinedTrades() {
  const nav = useNavigate();
  const { data: alerts } = useAlertsHistory(30);
  const declined = (alerts ?? [])
    .filter((a) => a.user_action === "skipped")
    .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));

  return (
    <div className="space-y-4">
      <p className="text-[12px] text-text-muted">
        Signals you <span className="text-text-secondary">passed on</span> — logged for review. <span className="text-text-faint">Coming: whether taking it would have worked (did it hit target before stop) — so you can see if your filtering is sharp.</span>
      </p>

      <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 inline-block">
        <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1">Declined · last 30 days</div>
        <div className="text-2xl font-mono font-bold text-text-primary">{declined.length}</div>
      </div>

      {declined.length > 0 ? (
        <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
          {declined.map((a) => {
            const d = (a.direction || "").toUpperCase();
            const long = d === "BUY" || d === "LONG";
            return (
              <div key={a.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 border-b border-border-subtle last:border-0">
                <span className="font-display text-[13px] font-semibold text-text-primary">{a.symbol}</span>
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
                {a.alert_type && (
                  <button onClick={() => nav(`/pattern/${encodeURIComponent(a.alert_type)}`)} title="Learn this pattern"
                    className="text-[11px] text-accent hover:underline shrink-0">{formatSetup(a.alert_type)}</button>
                )}
                <span className="font-mono text-[11px] text-text-muted tabular-nums">
                  {a.entry != null && <>entry {px(a.entry)}</>}
                  {a.target_1 != null && <> · target {px(a.target_1)}</>}
                  {a.stop != null && <> · stop {px(a.stop)}</>}
                </span>
                <span className="ml-auto text-[11px] text-text-faint">{when(a.created_at)}</span>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[13px] text-text-faint">
          No declined signals yet. Tap <span className="text-text-secondary">Decline</span> on a Today signal to start tracking what you passed on.
        </div>
      )}
    </div>
  );
}
