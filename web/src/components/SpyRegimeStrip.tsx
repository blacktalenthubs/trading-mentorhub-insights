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
    (r.pdl ? ` · PDL $${r.pdl.toFixed(2)}` : "") +
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
        <span className="font-semibold text-bearish-text">· ⛔ &lt; PDL · buys off</span>
      )}
      {r.rsi != null && (
        <span
          className={
            r.rsi_zone === "oversold" ? "text-accent font-semibold"
            : r.rsi_zone === "overbought" ? "text-warning-text font-semibold"
            : "text-text-faint"
          }
        >
          · RSI {r.rsi}{rsiZoned ? ` ${r.rsi_zone}` : ""}
        </span>
      )}
      {r.stale && <span className="text-warning-text" title="Live fetch failed — last known regime.">⚠</span>}
    </span>
  );
}

/* ── Risk posture — turns regime + RSI into a plain exposure command ──── */
type Posture = { word: string; tone: keyof typeof COLORS; hint: string };

function postureOf(r?: SpyRegimeSnapshot): Posture | null {
  if (!r || r.status !== "ok") return null;
  if (r.below_pdl)
    return { word: "STAND DOWN", tone: "red", hint: "below PDL — no new longs, reduce exposure; the tape can drag you anywhere" };
  if (r.rsi != null && r.rsi >= 70)
    return { word: "REDUCE", tone: "amber", hint: "overbought — trim & trade light" };
  if (r.rsi != null && r.rsi <= 30)
    return { word: "SIZE SMALL", tone: "amber", hint: "oversold bounce — not a trend, size small" };
  return { word: "NORMAL", tone: "green", hint: "stops on every position" };
}

function PostureChip({ label, p }: { label: string; p: Posture }) {
  const c = COLORS[p.tone];
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${c.bg}`} title={p.hint}>
      <span className="text-text-faint">{label}</span>
      <span className={`font-semibold ${c.text}`}>{p.word}</span>
    </span>
  );
}

/** A persistent risk reminder under the regime pills — "stops on" + the
 *  exposure call (STAND DOWN / REDUCE / SIZE SMALL / NORMAL) per market, so the
 *  Redler/Burns discipline stays in front of you every time you open the app. */
function RiskLine({ spy, btc }: { spy?: SpyRegimeSnapshot; btc?: SpyRegimeSnapshot }) {
  const sp = postureOf(spy);
  const bp = postureOf(btc);
  if (!sp && !bp) return null;
  return (
    <div className="inline-flex items-center gap-1.5 text-[11px] flex-wrap text-text-muted">
      <span className="font-semibold">🛡 Stops on every position</span>
      {sp && <PostureChip label="Stocks" p={sp} />}
      {bp && <PostureChip label="Crypto" p={bp} />}
    </div>
  );
}

export default function SpyRegimeStrip() {
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  if (!spy && !btc) return null;
  return (
    <div className="flex flex-col gap-1">
      <div className="inline-flex items-center gap-2 flex-wrap">
        <RegimeChip r={spy} label="SPY" />
        <RegimeChip r={btc} label="BTC" />
      </div>
      <RiskLine spy={spy} btc={btc} />
    </div>
  );
}
