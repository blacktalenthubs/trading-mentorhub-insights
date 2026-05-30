/** SPY Regime Strip — pinned at the top of the Trading page.
 *
 *  "Should I even trade today?" in one glance:
 *    Green LONG BIAS  — VWAP rising, price above → engage long setups
 *    Amber INSIDE DAY — opens between PDH and PDL → range expected, scalp edges
 *    Red STAND DOWN   — VWAP falling, price below → reduce or skip
 *    Gray NEUTRAL     — no clean direction
 *
 *  Polls every 60s. Reads from /market/spy-regime which caches 30s server-side.
 *  Outside market hours or pre-market, gracefully degrades to "unavailable".
 */

import { useSpyLiveRegime } from "../api/hooks";
import { Activity, AlertCircle } from "lucide-react";

const COLORS = {
  green: { bg: "bg-bullish/15", border: "border-bullish/40", text: "text-bullish-text", dot: "bg-bullish" },
  amber: { bg: "bg-warning/15", border: "border-warning/40", text: "text-warning-text", dot: "bg-warning" },
  red:   { bg: "bg-bearish/15", border: "border-bearish/40", text: "text-bearish-text", dot: "bg-bearish" },
  gray:  { bg: "bg-surface-3",  border: "border-border-subtle", text: "text-text-muted",  dot: "bg-text-faint" },
} as const;

export default function SpyRegimeStrip() {
  const { data: r, isLoading } = useSpyLiveRegime();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-2/40 border border-border-subtle rounded-md text-xs">
        <Activity className="h-3 w-3 text-text-faint animate-pulse" />
        <span className="text-text-faint">Loading SPY regime…</span>
      </div>
    );
  }

  if (!r || r.status !== "ok") {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-surface-2/40 border border-border-subtle rounded-md text-xs">
        <AlertCircle className="h-3 w-3 text-text-faint" />
        <span className="text-text-faint">SPY regime unavailable {r?.reason ? `(${r.reason})` : ""}</span>
      </div>
    );
  }

  const c = COLORS[r.bias_color ?? "gray"];
  const slopeSign = (r.vwap_slope_pct ?? 0) >= 0 ? "+" : "";
  const slope = `${slopeSign}${(r.vwap_slope_pct ?? 0).toFixed(2)}%`;

  return (
    <div
      className={`flex items-center gap-3 px-3 py-1.5 ${c.bg} border ${c.border} rounded-md text-xs`}
      title={r.bias_label}
    >
      <div className={`h-2 w-2 rounded-full ${c.dot} animate-pulse`} />
      <span className={`font-bold ${c.text}`}>
        SPY {r.bias === "WAIT" ? "INSIDE DAY" : r.bias?.replace("_", " ")}
      </span>
      <span className="text-text-muted">·</span>
      <span className="font-mono text-text-secondary">${r.price?.toFixed(2)}</span>
      <span className="text-text-muted">·</span>
      <span className="font-mono text-text-muted">
        VWAP {slope}
      </span>
      {r.inside_day && (
        <>
          <span className="text-text-muted">·</span>
          <span className="text-[10px] text-warning-text font-semibold">
            PDH ${r.pdh?.toFixed(2)} / PDL ${r.pdl?.toFixed(2)}
          </span>
        </>
      )}
      <span className={`ml-auto text-[10px] ${c.text} italic`}>
        {r.bias_label}
      </span>
    </div>
  );
}
