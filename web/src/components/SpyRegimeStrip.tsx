/** Market regime strips — pinned at the top of the Trading page.
 *
 *  ONE compact pill per market (SPY = stocks, BTC = crypto). Each pill folds
 *  bias + "buys off" (below PDL) + RSI-when-stretched into a single chip, with
 *  price/VWAP/PDL in the hover tooltip — so the row stays tidy instead of
 *  spreading 3 chips per market. Polls 60s; collapses while loading.
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
  if (!r) return null;  // still loading
  if (r.status !== "ok") {
    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 bg-surface-3 border border-border-subtle rounded-full text-[11px] text-text-muted"
        title={`${label} regime data unavailable — gate can't read ${label}'s PDL (market closed or data outage). Manual caution.`}
      >
        ⚠ {label} unavailable
      </span>
    );
  }

  const c = COLORS[r.bias_color ?? "gray"];
  const biasText = r.bias === "WAIT" ? "Inside Day" : (r.bias?.replace("_", " ") ?? "");
  const rsiZoned = r.rsi != null && r.rsi_zone && r.rsi_zone !== "neutral";
  const slopeSign = (r.vwap_slope_pct ?? 0) >= 0 ? "+" : "";
  const tip =
    `${label}: $${r.price?.toFixed(2)} · VWAP ${slopeSign}${(r.vwap_slope_pct ?? 0).toFixed(2)}% · ${r.bias_label}` +
    (r.rsi != null ? ` · RSI ${r.rsi}` : "");

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 ${c.bg} border ${c.border} rounded-full text-[11px]`}
      title={tip}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${c.dot}`} />
      <span className={`font-semibold ${c.text}`}>{label}</span>
      <span className={c.text}>{biasText}</span>
      {r.below_pdl && (
        <span
          className="font-semibold text-bearish-text"
          title="SPY is below its prior-day low — weak tape, buys off"
        >
          {`· ⛔ < PDL · buys off`}
        </span>
      )}
      {rsiZoned && (
        <span
          className={
            r.rsi_zone === "oversold" ? "text-accent font-semibold" : "text-warning-text font-semibold"
          }
        >
          · RSI {r.rsi} {r.rsi_zone}
        </span>
      )}
      {r.stale && <span className="text-warning-text" title="Live fetch failed — last known regime.">⚠</span>}
    </span>
  );
}

/* Risk posture / "stops on every position" line REMOVED 2026-07-03 — the platform
 * surfaces DATA (regime, levels), users decide their own risk; the educational
 * disclaimer covers it. The prescriptive NORMAL/REDUCE/STAND-DOWN line is gone;
 * SPY/BTC regime chips (informational market state) stay. */

export default function SpyRegimeStrip() {
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  if (!spy && !btc) return null;
  return (
    <div className="inline-flex items-center gap-2 flex-wrap">
      <RegimeChip r={spy} label="SPY" />
      <RegimeChip r={btc} label="BTC" />
    </div>
  );
}
