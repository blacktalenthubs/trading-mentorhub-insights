/** Market regime strips — pinned at the top of the Trading page.
 *
 *  Two gates at a glance:
 *    SPY  — the stock-market gate (RTH). Below its PDL → equity buys suppressed.
 *    BTC  — the crypto gate (24/7). Below its PDL → ETH/alt buys suppressed.
 *
 *  Each shows bias (LONG / INSIDE DAY / STAND DOWN / NEUTRAL) + price + VWAP
 *  slope, and a loud red "Buys suppressed · X < PDL" chip when below PDL — so a
 *  quiet feed reads as "gate active", not "no setups". Polls every 60s; server
 *  caches 30s. Degrades to nothing while loading/unavailable (zero space).
 */

import { useSpyLiveRegime, useBtcLiveRegime } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";

const COLORS = {
  green: { bg: "bg-bullish/15", border: "border-bullish/40", text: "text-bullish-text", dot: "bg-bullish" },
  amber: { bg: "bg-warning/15", border: "border-warning/40", text: "text-warning-text", dot: "bg-warning" },
  red:   { bg: "bg-bearish/15", border: "border-bearish/40", text: "text-bearish-text", dot: "bg-bearish" },
  gray:  { bg: "bg-surface-3",  border: "border-border-subtle", text: "text-text-muted",  dot: "bg-text-faint" },
} as const;

function RegimeChip({ r, label }: { r?: SpyRegimeSnapshot; label: string }) {
  // Collapse to nothing while loading/unavailable so it costs zero space.
  if (!r || r.status !== "ok") return null;

  const c = COLORS[r.bias_color ?? "gray"];
  const slopeSign = (r.vwap_slope_pct ?? 0) >= 0 ? "+" : "";
  const slope = `${slopeSign}${(r.vwap_slope_pct ?? 0).toFixed(2)}%`;
  const biasText = r.bias === "WAIT" ? "Inside Day" : (r.bias?.replace("_", " ") ?? "");

  return (
    <div className="inline-flex items-center gap-1.5">
      <div
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 ${c.bg} border ${c.border} rounded-full text-[11px]`}
        title={r.bias_label}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
        <span className={`font-semibold ${c.text}`}>{label} {biasText}</span>
        <span className="text-text-faint">·</span>
        <span className="font-mono text-text-muted">${r.price?.toFixed(2)}</span>
        <span className="font-mono text-text-faint">VWAP {slope}</span>
      </div>
      {r.below_pdl && (
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 bg-bearish/20 border border-bearish/50 rounded-full text-[11px] font-semibold text-bearish-text"
          title={`${label} is below its prior-day low${r.pdl ? ` ($${r.pdl.toFixed(2)})` : ""} — buy alerts suppressed until it reclaims. Don't counter-trend.`}
        >
          ⛔ Buys suppressed · {label} &lt; PDL
        </span>
      )}
    </div>
  );
}

export default function SpyRegimeStrip() {
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  // Render nothing if neither is available (keeps the row collapsed).
  if ((!spy || spy.status !== "ok") && (!btc || btc.status !== "ok")) return null;
  return (
    <div className="inline-flex items-center gap-2 flex-wrap">
      <RegimeChip r={spy} label="SPY" />
      <RegimeChip r={btc} label="BTC" />
    </div>
  );
}
