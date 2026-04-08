/** Structured trade plan card — shows direction, levels, R:R, confidence. */

import { TrendingUp, TrendingDown, Minus, AlertTriangle } from "lucide-react";

export interface TradePlan {
  setup: string | null;
  direction: string | null;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  rr_ratio: number | null;
  confidence: string | null;
  confluence_score: number | null;
  timeframe_fit: string | null;
  key_levels: string[];
  historical_ref: string | null;
}

function DirectionBadge({ direction }: { direction: string | null }) {
  if (!direction) return null;
  const d = direction.toUpperCase();
  if (d === "LONG") {
    return (
      <span className="inline-flex items-center gap-1.5 bg-bullish/10 border border-bullish/20 text-bullish-text text-xs font-bold px-2.5 py-1 rounded-md">
        <TrendingUp className="h-3.5 w-3.5" />
        LONG
      </span>
    );
  }
  if (d === "SHORT") {
    return (
      <span className="inline-flex items-center gap-1.5 bg-bearish/10 border border-bearish/20 text-bearish-text text-xs font-bold px-2.5 py-1 rounded-md">
        <TrendingDown className="h-3.5 w-3.5" />
        SHORT
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 bg-surface-3 border border-border-subtle text-text-faint text-xs font-bold px-2.5 py-1 rounded-md">
      <Minus className="h-3.5 w-3.5" />
      NO TRADE
    </span>
  );
}

function ConfidenceBadge({ confidence }: { confidence: string | null }) {
  if (!confidence) return null;
  const c = confidence.toUpperCase();
  const cls =
    c === "HIGH"
      ? "bg-bullish/10 text-bullish-text border-bullish/20"
      : c === "MEDIUM"
      ? "bg-warning/10 text-warning-text border-warning/20"
      : "bg-bearish/10 text-bearish-text border-bearish/20";
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${cls}`}>
      {c}
    </span>
  );
}

function PriceRow({ label, value, color }: { label: string; value: number | null; color?: string }) {
  if (value == null) return null;
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className={`text-xs font-mono font-semibold ${color || "text-text-primary"}`}>
        ${value.toFixed(2)}
      </span>
    </div>
  );
}

export default function TradePlanCard({ plan }: { plan: TradePlan }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-4 space-y-3">
      {/* Header: direction + confidence */}
      <div className="flex items-center justify-between">
        <DirectionBadge direction={plan.direction} />
        <ConfidenceBadge confidence={plan.confidence} />
      </div>

      {/* Setup name */}
      {plan.setup && plan.setup.toLowerCase() !== "n/a" && (
        <p className="text-xs font-semibold text-accent">{plan.setup}</p>
      )}

      {/* Price levels */}
      <div className="border-t border-border-subtle/50 pt-2">
        <PriceRow label="Entry" value={plan.entry} color="text-accent" />
        <PriceRow label="Stop" value={plan.stop} color="text-bearish-text" />
        <PriceRow label="Target 1" value={plan.target_1} color="text-bullish-text" />
        <PriceRow label="Target 2" value={plan.target_2} color="text-bullish-text" />
      </div>

      {/* R:R and Confluence */}
      <div className="flex items-center gap-4 border-t border-border-subtle/50 pt-2">
        {plan.rr_ratio != null && (
          <div>
            <span className="text-[10px] text-text-faint block">R:R</span>
            <span className="text-sm font-bold text-text-primary font-mono">
              1:{plan.rr_ratio.toFixed(1)}
            </span>
          </div>
        )}
        {plan.confluence_score != null && (
          <div>
            <span className="text-[10px] text-text-faint block">Confluence</span>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-bold text-text-primary font-mono">
                {plan.confluence_score}/10
              </span>
              {/* Mini bar */}
              <div className="w-16 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    plan.confluence_score >= 7
                      ? "bg-bullish"
                      : plan.confluence_score >= 4
                      ? "bg-warning"
                      : "bg-bearish"
                  }`}
                  style={{ width: `${(plan.confluence_score / 10) * 100}%` }}
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Timeframe fit */}
      {plan.timeframe_fit && (
        <p className="text-[10px] text-text-muted border-t border-border-subtle/50 pt-2">
          {plan.timeframe_fit}
        </p>
      )}

      {/* Key levels */}
      {plan.key_levels.length > 0 && (
        <div className="border-t border-border-subtle/50 pt-2">
          <span className="text-[10px] text-text-faint block mb-1">Key Levels</span>
          <div className="flex flex-wrap gap-1">
            {plan.key_levels.map((level, i) => (
              <span
                key={i}
                className="text-[10px] bg-surface-3 text-text-secondary px-1.5 py-0.5 rounded"
              >
                {level}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Historical reference */}
      {plan.historical_ref && (
        <p className="text-[10px] text-text-faint italic border-t border-border-subtle/50 pt-2">
          {plan.historical_ref}
        </p>
      )}

      {/* Disclaimer */}
      <div className="flex items-start gap-1.5 border-t border-border-subtle/50 pt-2">
        <AlertTriangle className="h-3 w-3 text-warning shrink-0 mt-0.5" />
        <p className="text-[9px] text-text-faint leading-tight">
          Not financial advice. AI analysis is for educational purposes only. Always do your own due diligence.
        </p>
      </div>
    </div>
  );
}
