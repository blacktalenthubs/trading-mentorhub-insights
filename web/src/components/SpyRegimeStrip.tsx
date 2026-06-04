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

const COLORS = {
  green: { bg: "bg-bullish/15", border: "border-bullish/40", text: "text-bullish-text", dot: "bg-bullish" },
  amber: { bg: "bg-warning/15", border: "border-warning/40", text: "text-warning-text", dot: "bg-warning" },
  red:   { bg: "bg-bearish/15", border: "border-bearish/40", text: "text-bearish-text", dot: "bg-bearish" },
  gray:  { bg: "bg-surface-3",  border: "border-border-subtle", text: "text-text-muted",  dot: "bg-text-faint" },
} as const;

export default function SpyRegimeStrip() {
  const { data: r, isLoading } = useSpyLiveRegime();

  // Compact pill — collapse to nothing while loading/unavailable so it costs
  // zero vertical space rather than a placeholder band.
  if (isLoading || !r || r.status !== "ok") return null;

  const c = COLORS[r.bias_color ?? "gray"];
  const slopeSign = (r.vwap_slope_pct ?? 0) >= 0 ? "+" : "";
  const slope = `${slopeSign}${(r.vwap_slope_pct ?? 0).toFixed(2)}%`;
  const biasText = r.bias === "WAIT" ? "Inside Day" : (r.bias?.replace("_", " ") ?? "");

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 ${c.bg} border ${c.border} rounded-full text-[11px]`}
      title={r.bias_label}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      <span className={`font-semibold ${c.text}`}>SPY {biasText}</span>
      <span className="text-text-faint">·</span>
      <span className="font-mono text-text-muted">${r.price?.toFixed(2)}</span>
      <span className="font-mono text-text-faint">VWAP {slope}</span>
    </div>
  );
}
