/** One Focus List recommendation — expandable to full qualifying detail. */

import { useState } from "react";
import {
  ArrowUp,
  ArrowDown,
  BarChart3,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { FocusRecommendation } from "../api/hooks";

const fmt = (v: number | null) => (v != null ? `$${v.toFixed(2)}` : "—");

function ConvictionBadge({ conviction }: { conviction: string }) {
  const cls =
    conviction === "HIGH"
      ? "bg-emerald-500/15 text-emerald-400"
      : conviction === "MEDIUM"
      ? "bg-yellow-500/15 text-yellow-400"
      : "bg-text-muted/15 text-text-muted";
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${cls}`}>
      {conviction}
    </span>
  );
}

export default function RecommendationCard({
  rec,
  onSelectSymbol,
}: {
  rec: FocusRecommendation;
  onSelectSymbol?: (symbol: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const isLong = rec.direction === "LONG";

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-1">
      <div className="p-3">
        <div className="flex items-start justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-text-primary">{rec.symbol}</span>
            <span
              className={`text-[10px] font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5 ${
                isLong
                  ? "bg-bullish/15 text-bullish-text border border-bullish/25"
                  : "bg-bearish/15 text-bearish-text border border-bearish/25"
              }`}
            >
              {isLong ? (
                <ArrowUp className="h-2.5 w-2.5" />
              ) : (
                <ArrowDown className="h-2.5 w-2.5" />
              )}
              {rec.direction}
            </span>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary uppercase tracking-wide">
              {rec.trade_horizon === "day_trade" ? "Day" : "Swing"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-bold text-accent">
              {rec.distance_to_entry_pct.toFixed(1)}% away
            </span>
            <ConvictionBadge conviction={rec.conviction} />
          </div>
        </div>

        <div className="text-xs text-text-secondary mb-2">{rec.setup_type}</div>

        <div className="grid grid-cols-4 gap-2 text-[11px] mb-1">
          <div>
            <div className="text-text-faint">Entry</div>
            <div className="font-mono text-text-primary font-bold">{fmt(rec.entry)}</div>
          </div>
          <div>
            <div className="text-text-faint">Stop</div>
            <div className="font-mono text-bearish-text">{fmt(rec.stop)}</div>
          </div>
          <div>
            <div className="text-text-faint">T1</div>
            <div className="font-mono text-bullish-text">{fmt(rec.t1)}</div>
          </div>
          <div>
            <div className="text-text-faint">T2</div>
            <div className="font-mono text-text-secondary">{fmt(rec.t2)}</div>
          </div>
        </div>
      </div>

      <div className="flex items-center border-t border-border-subtle/50">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex-1 flex items-center gap-1 px-3 py-1.5 text-[11px] text-text-muted hover:text-text-secondary transition-colors"
        >
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
          Why this qualifies
        </button>
        <button
          onClick={() => onSelectSymbol?.(rec.symbol)}
          className="px-3 py-1.5 text-[11px] text-text-secondary hover:text-accent transition-colors flex items-center gap-1 border-l border-border-subtle/50"
          title="Open this symbol's chart"
        >
          <BarChart3 className="h-3.5 w-3.5" />
          Chart
        </button>
      </div>

      {open && (
        <div className="px-3 pb-3 pt-1 space-y-2 border-t border-border-subtle/50">
          {rec.why_now && (
            <p className="text-[11px] text-text-muted italic">{rec.why_now}</p>
          )}
          <div>
            <div className="text-[10px] text-text-faint uppercase tracking-wide mb-1">
              Entry trigger
            </div>
            <div className="text-[11px] text-text-secondary">
              {rec.qualifying_criteria.entry_trigger || rec.setup_type}
            </div>
          </div>
          {rec.qualifying_criteria.conviction_drivers.length > 0 && (
            <div>
              <div className="text-[10px] text-text-faint uppercase tracking-wide mb-1">
                Conviction drivers
              </div>
              <div className="flex flex-wrap gap-1">
                {rec.qualifying_criteria.conviction_drivers.map((c, i) => (
                  <span
                    key={i}
                    className="text-[10px] bg-accent/10 text-accent px-1.5 py-0.5 rounded"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="text-[10px] text-text-faint">
            Suits a{" "}
            <span className="text-text-secondary font-medium">
              {rec.trade_horizon === "day_trade" ? "day-trade" : "swing"}
            </span>{" "}
            hold.
          </div>
        </div>
      )}
    </div>
  );
}
