/** Premarket sector heat — per watchlist group aggregation. */

import { useState } from "react";
import { useGroupsPremarket, type GroupPremarketSummary, type GroupSymbolQuote } from "../api/hooks";
import Card from "../components/ui/Card";
import { Loader2, RefreshCw, TrendingUp, TrendingDown, Activity, ChevronDown, ChevronRight } from "lucide-react";

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function pctClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "text-text-faint";
  if (v > 0.5) return "text-bullish-text";
  if (v < -0.5) return "text-bearish-text";
  return "text-text-muted";
}

function arrowIcon(v: number | null | undefined) {
  if (v === null || v === undefined) return <Activity className="h-4 w-4 text-text-faint" />;
  if (v > 0.5) return <TrendingUp className="h-4 w-4 text-bullish-text" />;
  if (v < -0.5) return <TrendingDown className="h-4 w-4 text-bearish-text" />;
  return <Activity className="h-4 w-4 text-text-muted" />;
}

function ItemRow({ q }: { q: GroupSymbolQuote }) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2 last:border-b-0">
      <span className="text-sm font-semibold text-text-primary">{q.symbol}</span>
      <div className="flex items-center gap-4 text-xs">
        {q.last_price != null && (
          <span className="text-text-muted">${q.last_price.toFixed(2)}</span>
        )}
        <span className={`font-mono font-semibold ${pctClass(q.gap_pct)}`}>
          {fmtPct(q.gap_pct)}
        </span>
      </div>
    </div>
  );
}

function GroupCard({ g }: { g: GroupPremarketSummary }) {
  const [expanded, setExpanded] = useState(false);
  const breadth = g.breadth_total > 0 ? `${g.breadth_green}/${g.breadth_total}` : "—";
  const cardBorder = g.avg_gap_pct === null
    ? "border-border-subtle"
    : g.avg_gap_pct > 0.5
      ? "border-bullish/40"
      : g.avg_gap_pct < -0.5
        ? "border-bearish/40"
        : "border-border-subtle";

  return (
    <Card padding="none" className={`border ${cardBorder}`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-surface-3/50"
      >
        <div className="flex items-center gap-3">
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronRight className="h-4 w-4 text-text-muted" />
          )}
          {g.color && (
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: g.color }} />
          )}
          <span className="text-sm font-semibold text-text-primary">{g.name}</span>
          <span className="rounded-full bg-surface-4 px-2 py-0.5 text-xs text-text-muted">
            {g.item_count}
          </span>
        </div>
        <div className="flex items-center gap-5 text-xs">
          <div className="flex items-center gap-1.5">
            {arrowIcon(g.avg_gap_pct)}
            <span className={`font-mono font-semibold text-sm ${pctClass(g.avg_gap_pct)}`}>
              {fmtPct(g.avg_gap_pct)}
            </span>
          </div>
          <span className="text-text-muted hidden sm:inline">breadth {breadth}</span>
          {g.top_mover && (
            <span className="text-text-muted hidden md:inline">
              <span className="text-bullish-text">▲</span> {g.top_mover.symbol} {fmtPct(g.top_mover.gap_pct)}
            </span>
          )}
          {g.bottom_mover && g.bottom_mover.symbol !== g.top_mover?.symbol && (
            <span className="text-text-muted hidden md:inline">
              <span className="text-bearish-text">▼</span> {g.bottom_mover.symbol} {fmtPct(g.bottom_mover.gap_pct)}
            </span>
          )}
        </div>
      </button>
      {expanded && g.items.length > 0 && (
        <div className="border-t border-border-subtle">
          {g.items
            .slice()
            .sort((a, b) => (b.gap_pct ?? -999) - (a.gap_pct ?? -999))
            .map((it) => (
              <ItemRow key={it.symbol} q={it} />
            ))}
        </div>
      )}
    </Card>
  );
}

export default function PremarketPage() {
  const { data, isLoading, isFetching, refetch, error } = useGroupsPremarket();

  return (
    <div className="h-full overflow-y-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-accent" />
          <h1 className="font-display text-2xl font-bold">Premarket Sector Heat</h1>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 rounded-lg bg-surface-3 px-3 py-2 text-xs font-medium text-text-primary transition-colors hover:bg-surface-4 disabled:opacity-40 active:scale-95"
        >
          {isFetching ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Refresh
        </button>
      </div>

      <p className="text-sm text-text-muted">
        Per-group aggregation across your watchlist sectors. Sorted by absolute movement so the most active sectors float to top. Click a card to drill into per-symbol moves.
      </p>

      {isLoading && (
        <div className="flex items-center gap-2 py-8">
          <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          <span className="text-sm text-text-muted">Loading sector data...</span>
        </div>
      )}

      {error && (
        <Card padding="md">
          <p className="text-sm text-bearish-text">
            {error instanceof Error ? error.message : "Failed to load premarket data"}
          </p>
        </Card>
      )}

      {data && data.length === 0 && (
        <Card padding="md">
          <p className="text-sm text-text-muted">
            No watchlist groups found. Go to <a href="/watchlist" className="text-accent hover:underline">Watchlist</a> and click <strong>Seed Default Groups</strong> to populate sectors.
          </p>
        </Card>
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((g) => (
            <GroupCard key={g.group_id} g={g} />
          ))}
        </div>
      )}
    </div>
  );
}
