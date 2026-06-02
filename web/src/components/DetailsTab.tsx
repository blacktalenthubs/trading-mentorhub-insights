/** Details tab inside the Watchlist page.
 *
 *  For each watchlist symbol, a card with the company context a trader needs to
 *  judge a position:
 *    - What the company does (yfinance business summary)
 *    - Analyst ratings (Finnhub buy/hold/sell distribution + consensus)
 *    - EPS strength (trailing / forward EPS, growth, P/E)
 *    - AI-generated short-term and long-term views
 *
 *  Data is fetched/generated ON DEMAND and cached server-side. Each card has a
 *  Refresh button; the header has "Refresh all". Un-fetched symbols show a
 *  prompt to refresh rather than empty fields.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useWatchlistFundamentals,
  useRefreshFundamentals,
  type FundamentalsItem,
} from "../api/hooks";
import Card from "./ui/Card";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import {
  Info, AlertCircle, RefreshCw, Loader2, ChevronDown, ChevronRight,
} from "lucide-react";

function fmtRelativeAge(iso: string | null): string {
  if (!iso) return "never";
  const diffH = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (diffH < 1) return "just now";
  if (diffH < 24) return `${Math.round(diffH)}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}

function fmtMarketCap(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}

function consensusColor(c: string | null): string {
  if (c === "Buy") return "text-bullish-text";
  if (c === "Sell") return "text-bearish-text";
  if (c === "Hold") return "text-warning-text";
  return "text-text-faint";
}

function growthColor(g: number | null): string {
  if (g == null) return "text-text-faint";
  return g > 0 ? "text-bullish-text" : g < 0 ? "text-bearish-text" : "text-text-muted";
}

/* ── Analyst rating distribution bar ─────────────────────────────── */

function RatingBar({ it }: { it: FundamentalsItem }) {
  const sb = it.rec_strong_buy ?? 0;
  const b = it.rec_buy ?? 0;
  const h = it.rec_hold ?? 0;
  const s = it.rec_sell ?? 0;
  const ss = it.rec_strong_sell ?? 0;
  const total = sb + b + h + s + ss;
  if (total === 0) {
    return <span className="text-[11px] text-text-faint">No analyst coverage</span>;
  }
  const seg = (n: number, cls: string) =>
    n > 0 ? <div className={cls} style={{ width: `${(n / total) * 100}%` }} /> : null;
  return (
    <div className="space-y-1">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-3">
        {seg(sb, "bg-bullish")}
        {seg(b, "bg-bullish/60")}
        {seg(h, "bg-warning/70")}
        {seg(s, "bg-bearish/60")}
        {seg(ss, "bg-bearish")}
      </div>
      <div className="flex items-center justify-between text-[10px] text-text-faint">
        <span>{total} analyst{total === 1 ? "" : "s"}</span>
        <span className="font-mono">
          {sb + b} buy · {h} hold · {s + ss} sell
        </span>
      </div>
    </div>
  );
}

/* ── A single field cell ─────────────────────────────────────────── */

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-text-faint">{label}</span>
      <span className={`text-sm font-mono ${color ?? "text-text-secondary"}`}>{value}</span>
    </div>
  );
}

/* ── One symbol card ─────────────────────────────────────────────── */

function DetailCard({
  it, onOpen, onRefresh, refreshing,
}: {
  it: FundamentalsItem;
  onOpen: () => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [showFull, setShowFull] = useState(false);
  const fetched = it.fetched_at != null;
  const desc = it.description ?? "";
  const long = desc.length > 220;

  return (
    <Card padding="md" className="space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <button onClick={onOpen} className="text-left">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-semibold text-text-primary">{it.symbol}</span>
            {it.consensus && (
              <span className={`text-[11px] font-semibold ${consensusColor(it.consensus)}`}>
                {it.consensus}
              </span>
            )}
          </div>
          <div className="text-[11px] text-text-muted">
            {it.company_name || "—"}
            {it.industry && <span className="text-text-faint"> · {it.industry}</span>}
          </div>
        </button>
        <button
          onClick={onRefresh}
          disabled={refreshing}
          className="flex items-center gap-1 rounded-md bg-surface-3 px-2 py-1 text-[10px] font-medium text-text-secondary transition-colors hover:bg-surface-4 disabled:opacity-40 active:scale-95"
        >
          {refreshing ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          {fetched ? "Refresh" : "Fetch"}
        </button>
      </div>

      {!fetched ? (
        <p className="text-[11px] text-text-faint">
          Not fetched yet — tap Fetch to load fundamentals, analyst ratings, and the AI view.
        </p>
      ) : (
        <>
          {/* Description */}
          {desc && (
            <div className="text-[11px] leading-relaxed text-text-muted">
              {long && !showFull ? `${desc.slice(0, 220)}…` : desc}
              {long && (
                <button
                  onClick={() => setShowFull(v => !v)}
                  className="ml-1 inline-flex items-center text-accent"
                >
                  {showFull ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  {showFull ? "less" : "more"}
                </button>
              )}
            </div>
          )}

          {/* EPS strength + valuation */}
          <div className="grid grid-cols-4 gap-2">
            <Stat label="EPS (ttm)" value={it.trailing_eps != null ? `$${it.trailing_eps.toFixed(2)}` : "—"} />
            <Stat label="EPS (fwd)" value={it.forward_eps != null ? `$${it.forward_eps.toFixed(2)}` : "—"} />
            <Stat
              label="EPS growth"
              value={it.eps_growth_pct != null ? `${it.eps_growth_pct > 0 ? "+" : ""}${it.eps_growth_pct.toFixed(1)}%` : "—"}
              color={growthColor(it.eps_growth_pct)}
            />
            <Stat label="P/E" value={it.pe_ratio != null ? it.pe_ratio.toFixed(1) : "—"} />
          </div>

          {/* Analyst ratings */}
          <RatingBar it={it} />

          {/* AI views */}
          <div className="space-y-2 border-t border-border-subtle/40 pt-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent">Short-term view</div>
              <p className="text-[11px] leading-relaxed text-text-secondary">
                {it.short_term_view || <span className="text-text-faint italic">AI view unavailable — tap Refresh.</span>}
              </p>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-accent">Long-term view</div>
              <p className="text-[11px] leading-relaxed text-text-secondary">
                {it.long_term_view || <span className="text-text-faint italic">AI view unavailable — tap Refresh.</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between text-[10px] text-text-faint">
            <span>Market cap {fmtMarketCap(it.market_cap)}</span>
            <span>Updated {fmtRelativeAge(it.fetched_at)}</span>
          </div>
        </>
      )}
    </Card>
  );
}

/* ── Main tab ─────────────────────────────────────────────────────── */

export default function DetailsTab() {
  const { data, isLoading, error } = useWatchlistFundamentals();
  const refresh = useRefreshFundamentals();
  const navigate = useNavigate();

  function openSymbol(symbol: string) {
    navigate(`/trading?symbol=${encodeURIComponent(symbol)}`);
  }

  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <div className="flex items-center justify-between">
          <Skeleton w={180} h={12} />
          <Skeleton w={100} h={24} />
        </div>
        <SkeletonRow count={4} h={160} gap={12} />
      </div>
    );
  }
  if (error) {
    return (
      <Card padding="md">
        <div className="flex items-center gap-2 text-bearish-text">
          <AlertCircle className="h-4 w-4" />
          <span className="text-sm">Failed to load details.</span>
        </div>
      </Card>
    );
  }

  const items = data?.items ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        icon={Info}
        title="No symbols to detail yet"
        hint="Company fundamentals, analyst ratings, and AI views are pulled for the tickers on your watchlist. Add a few symbols and they'll appear here."
        primary={{ label: "Edit watchlist", to: "/watchlist" }}
      />
    );
  }

  // TanStack v5: `refresh.variables` is the symbol passed to the in-flight
  // mutation (undefined for "refresh all").
  const refreshingAll = refresh.isPending && refresh.variables === undefined;
  const refreshingSymbol = refresh.isPending ? (refresh.variables as string | undefined) : undefined;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-text-faint">
        <span>Updated {fmtRelativeAge(data?.last_refreshed_at ?? null)}</span>
        <button
          onClick={() => refresh.mutate(undefined)}
          disabled={refresh.isPending}
          className="flex items-center gap-1.5 rounded-md bg-surface-3 px-2.5 py-1.5 text-[11px] font-medium text-text-secondary transition-colors hover:bg-surface-4 disabled:opacity-40 active:scale-95"
        >
          {refreshingAll ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Refresh all
        </button>
      </div>

      {refreshingAll && (
        <p className="text-[10px] text-text-faint">
          Refreshing all symbols — this can take a minute or two (throttled data + AI views).
        </p>
      )}

      <div className="space-y-3">
        {items.map(it => (
          <DetailCard
            key={it.symbol}
            it={it}
            onOpen={() => openSymbol(it.symbol)}
            onRefresh={() => refresh.mutate(it.symbol)}
            refreshing={refreshingAll || refreshingSymbol === it.symbol}
          />
        ))}
      </div>
    </div>
  );
}
