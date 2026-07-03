/** Alert Log — the v4.2-inspired running tape of everything that fired this session.
 *
 *  A terse, chronological (newest-first) stream of ALL feed alerts — every symbol,
 *  every style, delivered or not — one line each. It's the raw "what's been firing"
 *  view, distinct from the Signals feed (which is filtered + shown as rich cards).
 *  Same data (the session's alerts), a different lens. Click a row → jump the chart.
 */

import type { Alert } from "../types";
import { formatSetup, isFeedSignal } from "../lib/alertFormat";

function timeOf(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Chicago",
  });
}

export default function AlertLog({
  alerts,
  onSelectSymbol,
}: {
  alerts: Alert[] | undefined;
  onSelectSymbol: (s: string) => void;
}) {
  const Msg = ({ children }: { children: React.ReactNode }) => (
    <div className="flex-1 flex items-center justify-center p-4">
      <p className="text-xs text-text-faint text-center">{children}</p>
    </div>
  );

  if (alerts === undefined) return <Msg>Loading…</Msg>;

  const log = alerts
    .filter((a) => isFeedSignal(a.alert_type))
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  if (log.length === 0) return <Msg>No alerts this session</Msg>;

  return (
    <div className="flex-1 overflow-y-auto px-3 py-1 font-mono text-[11px]">
      {log.map((a) => {
        const dir = a.direction === "BUY" ? "LONG" : a.direction === "SHORT" ? "SHORT" : null;
        const dirCls =
          a.direction === "BUY" ? "text-bullish-text"
          : a.direction === "SHORT" ? "text-bearish-text"
          : "text-text-muted";
        const notSent = !!a.suppressed_reason;
        const rr =
          a.entry != null && a.target_1 != null && a.stop != null && a.entry !== a.stop
            ? Math.abs((a.target_1 - a.entry) / (a.entry - a.stop))
            : null;
        return (
          <button
            key={a.id}
            onClick={() => onSelectSymbol(a.symbol)}
            title={notSent ? "Recorded, not delivered" : undefined}
            className={`w-full text-left flex items-center gap-2 py-1.5 border-b border-border-subtle/40 hover:bg-surface-2 transition-colors ${notSent ? "opacity-45" : ""}`}
          >
            <span className="shrink-0 tabular-nums text-text-faint">{timeOf(a.created_at)}</span>
            <span className="shrink-0 font-bold text-text-primary">{a.symbol}</span>
            {dir && <span className={`shrink-0 font-semibold ${dirCls}`}>{dir}</span>}
            <span className="flex-1 truncate text-text-muted">{formatSetup(a.alert_type)}</span>
            {rr != null && (
              <span className={`shrink-0 font-bold ${rr >= 2 ? "text-bullish-text" : "text-text-faint"}`}>
                {rr.toFixed(1)}R
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
