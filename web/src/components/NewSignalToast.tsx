/** New-signal pop-up — a small floating card that surfaces a freshly-fired
 *  signal over the chart, so the user doesn't miss it while the Signals panel
 *  is collapsed. Tap to jump the chart to that symbol + expand the panel.
 *  Auto-dismiss is handled by the parent (TradingPageV2).
 */

import { X, Zap } from "lucide-react";
import { formatSetup } from "../lib/alertFormat";
import type { Alert } from "../types";

export default function NewSignalToast({
  alert, onTap, onDismiss,
}: {
  alert: Alert;
  onTap: () => void;
  onDismiss: () => void;
}) {
  const isLong = ["BUY", "LONG"].includes((alert.direction || "").toUpperCase());
  const grade = (alert.grade || "").toUpperCase();

  return (
    <div className="absolute top-2 left-1/2 -translate-x-1/2 z-30 w-[min(92%,360px)] pointer-events-none">
      <button
        onClick={onTap}
        className="pointer-events-auto w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-accent/40 bg-surface-2/95 backdrop-blur shadow-elevated text-left active:scale-[0.99] transition-transform"
      >
        <Zap className="h-4 w-4 text-accent shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-xs">
            <span className="font-semibold text-text-primary">{alert.symbol}</span>
            <span className={`text-[10px] font-bold ${isLong ? "text-bullish-text" : "text-bearish-text"}`}>
              {isLong ? "LONG" : "SHORT"}
            </span>
            {grade && (
              <span className="text-[10px] font-bold px-1 rounded bg-accent/15 text-accent">{grade}</span>
            )}
            <span className="ml-auto text-[10px] text-text-faint">new signal</span>
          </div>
          <div className="text-[11px] text-text-muted truncate">
            {formatSetup(alert.alert_type)}
            {alert.entry != null && ` · entry $${alert.entry.toFixed(2)}`}
          </div>
        </div>
        <span
          role="button"
          aria-label="Dismiss"
          onClick={(e) => { e.stopPropagation(); onDismiss(); }}
          className="p-1 -mr-1 text-text-faint hover:text-text-secondary shrink-0"
        >
          <X className="h-3.5 w-3.5" />
        </span>
      </button>
    </div>
  );
}
