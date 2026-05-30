/** Earnings tab inside the Watchlist page — spec 61 Phase 2.
 *
 *  Pulls the user's watchlist symbols sorted by next earnings date and
 *  surfaces: days-until, date, BMO/AMC, EPS estimate, last quarter's
 *  surprise %. Symbols inside the 0-7 day window are tinted amber to
 *  match the T-7 notification trigger. Symbols with no Finnhub data
 *  show as "—" so the user knows we tried.
 */

import { useUpcomingEarnings } from "../api/hooks";
import Card from "./ui/Card";
import { CalendarDays, Loader2, AlertCircle } from "lucide-react";

function fmtRelativeAge(iso: string | null): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffH = (now - then) / 3_600_000;
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  const days = Math.round(diffH / 24);
  return `${days}d ago`;
}

export default function EarningsTab() {
  const { data, isLoading, error } = useUpcomingEarnings();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-12 justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
        <span className="text-sm text-text-muted">Loading earnings…</span>
      </div>
    );
  }

  if (error) {
    return (
      <Card padding="md">
        <div className="flex items-center gap-2 text-bearish-text">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">Failed to load earnings.</span>
        </div>
      </Card>
    );
  }

  const items = data?.items ?? [];
  const withDate = items.filter(i => i.next_earnings_date);
  const noDate = items.filter(i => !i.next_earnings_date);

  // Stale-data warning if fetched > 36h ago.
  const refreshedIso = data?.last_refreshed_at ?? null;
  const stale = refreshedIso
    ? (Date.now() - new Date(refreshedIso).getTime()) / 3_600_000 > 36
    : false;

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <CalendarDays className="h-10 w-10 text-text-faint" />
        <p className="text-text-muted">No watchlist symbols yet</p>
        <p className="text-sm text-text-faint">Add symbols on the Symbols tab to start tracking earnings.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header strip with refresh status */}
      <div className="flex items-center justify-between text-xs text-text-faint">
        <span>
          {withDate.length} upcoming · {noDate.length} no calendar data
        </span>
        <span className={stale ? "text-warning-text" : ""}>
          Refreshed {fmtRelativeAge(refreshedIso)}
          {stale && " · data may be stale"}
        </span>
      </div>

      <Card padding="none">
        {/* Column headers */}
        <div className="grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint font-medium border-b border-border-subtle/50 bg-surface-2/30">
          <span className="col-span-2">Symbol</span>
          <span className="col-span-1 text-right">Days</span>
          <span className="col-span-2">Date</span>
          <span className="col-span-1 text-center">When</span>
          <span className="col-span-2 text-right">EPS Est</span>
          <span className="col-span-2 text-right">Last Q Surprise</span>
          <span className="col-span-2 text-right">Confirmed</span>
        </div>

        {withDate.map((it) => {
          const daysUntil = it.days_until;
          const inWindow = daysUntil != null && daysUntil >= 0 && daysUntil <= 7;
          const past = daysUntil != null && daysUntil < 0;
          const rowBg = inWindow ? "bg-warning/8" : past ? "opacity-50" : "";
          const dayColor = past ? "text-text-faint"
            : inWindow ? "text-warning-text font-semibold"
            : daysUntil != null && daysUntil <= 14 ? "text-text-primary"
            : "text-text-muted";

          const dateStr = it.next_earnings_date
            ? new Date(it.next_earnings_date + "T12:00:00").toLocaleDateString("en-US", {
              month: "short", day: "numeric", year: "numeric",
            })
            : "—";

          const surprise = it.last_surprise_pct;
          const surpriseColor = surprise == null ? "text-text-faint"
            : surprise > 0 ? "text-bullish-text"
            : surprise < 0 ? "text-bearish-text" : "text-text-muted";
          const surpriseStr = surprise == null ? "—"
            : `${surprise > 0 ? "+" : ""}${surprise.toFixed(1)}%`;

          return (
            <div
              key={it.symbol}
              className={`grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border-subtle/30 last:border-b-0 items-center text-xs ${rowBg}`}
            >
              <span className="col-span-2 font-semibold text-text-primary">{it.symbol}</span>
              <span className={`col-span-1 text-right font-mono ${dayColor}`}>
                {daysUntil == null ? "—" : daysUntil < 0 ? "past" : daysUntil}
              </span>
              <span className="col-span-2 text-text-secondary">{dateStr}</span>
              <span className="col-span-1 text-center text-[10px] font-mono text-text-muted">
                {it.time_of_day || "—"}
              </span>
              <span className="col-span-2 text-right font-mono text-text-secondary">
                {it.eps_estimate != null ? `$${it.eps_estimate.toFixed(2)}` : "—"}
              </span>
              <span className={`col-span-2 text-right font-mono font-semibold ${surpriseColor}`}>
                {surpriseStr}
                {it.last_quarter_label && surprise != null && (
                  <span className="text-[10px] font-normal text-text-faint ml-1">{it.last_quarter_label}</span>
                )}
              </span>
              <span className="col-span-2 text-right">
                {it.confirmed ? (
                  <span className="text-[10px] font-semibold text-bullish-text">CONFIRMED</span>
                ) : (
                  <span className="text-[10px] text-text-faint">estimate</span>
                )}
              </span>
            </div>
          );
        })}

        {noDate.length > 0 && (
          <>
            <div className="grid grid-cols-12 gap-2 px-4 py-1.5 text-[10px] uppercase tracking-wider text-text-faint font-medium bg-surface-2/20 border-t border-border-subtle/40">
              <span className="col-span-12">No upcoming earnings ({noDate.length}) — typically ETFs, crypto, or symbols outside our calendar coverage</span>
            </div>
            {noDate.map((it) => (
              <div
                key={it.symbol}
                className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/30 last:border-b-0 items-center text-xs text-text-faint"
              >
                <span className="col-span-2 font-semibold">{it.symbol}</span>
                <span className="col-span-10">—</span>
              </div>
            ))}
          </>
        )}
      </Card>
    </div>
  );
}
