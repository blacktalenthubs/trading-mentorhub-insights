/** Renders one saved Focus List — header + window-emphasised recommendation groups. */

import { AlertTriangle, Clock, Sparkles } from "lucide-react";
import RecommendationCard from "./RecommendationCard";
import type { FocusList, FocusRecommendation, MarketWindow, TradeHorizon } from "../api/hooks";

const WINDOW_LABEL: Record<MarketWindow, string> = {
  pre_open: "Pre-open run",
  pre_close: "Pre-close run",
  other: "Mid-session run",
};

/** Pre-open emphasises day-trade setups; pre-close emphasises swing setups. */
function emphasisFor(window: MarketWindow): TradeHorizon {
  return window === "pre_close" ? "swing" : "day_trade";
}

function formatGeneratedAt(iso: string): string {
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Group({
  horizon,
  recs,
  emphasised,
  onSelectSymbol,
}: {
  horizon: TradeHorizon;
  recs: FocusRecommendation[];
  emphasised: boolean;
  onSelectSymbol?: (s: string) => void;
}) {
  const title = horizon === "day_trade" ? "Day-Trade Setups" : "Swing Setups";
  return (
    <section className={emphasised ? "rounded-xl ring-1 ring-accent/30 bg-accent/[0.03] p-3" : "p-3"}>
      <div className="flex items-center gap-2 mb-2">
        <h3 className="text-xs font-bold uppercase tracking-wide text-text-secondary">
          {title}
        </h3>
        <span className="text-[10px] text-text-faint">({recs.length})</span>
        {emphasised && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-accent/15 text-accent flex items-center gap-1">
            <Sparkles className="h-2.5 w-2.5" />
            Today's focus
          </span>
        )}
      </div>
      {recs.length === 0 ? (
        <p className="text-[11px] text-text-muted italic py-2">
          No {horizon === "day_trade" ? "day-trade" : "swing"} setups in this scan.
        </p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {recs.map((r, i) => (
            <RecommendationCard
              key={`${r.symbol}-${i}`}
              rec={r}
              onSelectSymbol={onSelectSymbol}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export default function FocusListView({
  list,
  onSelectSymbol,
}: {
  list: FocusList;
  onSelectSymbol?: (symbol: string) => void;
}) {
  const day = list.recommendations.filter((r) => r.trade_horizon === "day_trade");
  const swing = list.recommendations.filter((r) => r.trade_horizon === "swing");
  const emphasis = emphasisFor(list.market_window);

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="font-bold px-2 py-1 rounded bg-surface-2 text-text-secondary">
          {WINDOW_LABEL[list.market_window]}
        </span>
        <span className="flex items-center gap-1 text-text-muted">
          <Clock className="h-3 w-3" />
          {formatGeneratedAt(list.generated_at)}
        </span>
        {list.is_stale ? (
          <span className="px-2 py-1 rounded bg-amber-500/15 text-amber-400 font-medium">
            Previous session — run a fresh scan
          </span>
        ) : (
          <span className="px-2 py-1 rounded bg-emerald-500/15 text-emerald-400 font-medium">
            Current
          </span>
        )}
        {list.watchlist_size > 0 && (
          <span className="text-text-faint">{list.watchlist_size} symbols scanned</span>
        )}
      </div>

      {/* Body */}
      {list.status === "failed" && (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-300">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>
            This scan failed — {list.message || "the AI scan could not complete"}. Your
            previous focus list is still available.
          </span>
        </div>
      )}

      {list.status === "no_setups" && (
        <div className="rounded-lg border border-border-subtle bg-surface-1 p-4 text-center text-xs text-text-muted">
          {list.message || "No qualifying setups in this scan."}
        </div>
      )}

      {list.status === "has_setups" && (
        <div className="space-y-3">
          {emphasis === "day_trade" ? (
            <>
              <Group horizon="day_trade" recs={day} emphasised onSelectSymbol={onSelectSymbol} />
              <Group horizon="swing" recs={swing} emphasised={false} onSelectSymbol={onSelectSymbol} />
            </>
          ) : (
            <>
              <Group horizon="swing" recs={swing} emphasised onSelectSymbol={onSelectSymbol} />
              <Group horizon="day_trade" recs={day} emphasised={false} onSelectSymbol={onSelectSymbol} />
            </>
          )}
        </div>
      )}

      {list.skipped.length > 0 && (
        <details className="text-[10px] text-text-faint">
          <summary className="cursor-pointer hover:text-text-muted">
            Skipped {list.skipped.length} symbol{list.skipped.length !== 1 ? "s" : ""}
          </summary>
          <ul className="mt-1 space-y-0.5 pl-2">
            {list.skipped.map((s, i) => (
              <li key={i} className="truncate">
                <span className="font-mono text-text-muted">{s.symbol}</span> — {s.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
