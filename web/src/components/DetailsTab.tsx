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
  useGenerateAIBrief,
  useMe,
  type FundamentalsItem,
  type AIBrief,
} from "../api/hooks";
import Card from "./ui/Card";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import {
  Info, AlertCircle, RefreshCw, Loader2, ChevronDown, ChevronRight, Sparkles, Search,
} from "lucide-react";

/** AI brief: regenerating it costs LLM, so only the admin who pays for it can.
 *  Mirrors require_ai_access on the backend (the endpoint 403s for everyone else). */
const AI_ADMIN_EMAIL = "vbolofinde@gmail.com";

const BRIEF_SECTIONS: { key: keyof AIBrief; label: string }[] = [
  { key: "business", label: "Business & moat" },
  { key: "growth", label: "Growth & margins" },
  { key: "valuation", label: "Valuation" },
  { key: "analyst", label: "Analyst take" },
  { key: "bull_case", label: "Bull case" },
  { key: "risks", label: "Key risks" },
  { key: "short_term", label: "Short-term" },
  { key: "long_term", label: "Long-term" },
];

function pctText(v: number | null | undefined): string {
  return v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—";
}

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

function consensusBadge(c: string | null): string {
  if (c === "Buy") return "bg-bullish-subtle text-bullish-text";
  if (c === "Sell") return "bg-bearish-subtle text-bearish-text";
  if (c === "Hold") return "bg-warning-subtle text-warning-text";
  return "bg-surface-3 text-text-faint";
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

/* ── Extra decision metrics (revenue growth, margins, 52w, vs MAs) ── */

function MetricsRow({ it }: { it: FundamentalsItem }) {
  const m = it.metrics;
  if (!m) return null;
  const range =
    m.last_price != null && m.week52_high != null && m.week52_low != null && m.week52_high > m.week52_low
      ? Math.round(((m.last_price - m.week52_low) / (m.week52_high - m.week52_low)) * 100)
      : null;
  const vsMa = (ma: number | null) =>
    m.last_price != null && ma != null
      ? { above: m.last_price >= ma, txt: `${m.last_price >= ma ? "+" : ""}${(((m.last_price - ma) / ma) * 100).toFixed(0)}%` }
      : null;
  const ma50 = vsMa(m.ma50);
  const ma200 = vsMa(m.ma200);
  const has = m.revenue_growth_pct != null || m.gross_margin_pct != null || ma50 || range != null;
  if (!has) return null;
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
      <Stat label="Rev growth" value={pctText(m.revenue_growth_pct)} color={growthColor(m.revenue_growth_pct)} />
      <Stat label="Gross mgn" value={m.gross_margin_pct != null ? `${m.gross_margin_pct.toFixed(0)}%` : "—"} />
      <Stat label="Net mgn" value={m.net_margin_pct != null ? `${m.net_margin_pct.toFixed(0)}%` : "—"} color={growthColor(m.net_margin_pct)} />
      <Stat label="vs 50DMA" value={ma50 ? ma50.txt : "—"} color={ma50 ? (ma50.above ? "text-bullish-text" : "text-bearish-text") : undefined} />
      <Stat label="vs 200DMA" value={ma200 ? ma200.txt : "—"} color={ma200 ? (ma200.above ? "text-bullish-text" : "text-bearish-text") : undefined} />
      <Stat label="52w range" value={range != null ? `${range}%` : "—"} />
    </div>
  );
}

/* ── Structured AI investment brief ──────────────────────────────── */

function BriefView({ brief }: { brief: AIBrief }) {
  return (
    <div className="space-y-2">
      {brief.summary && (
        <p className="text-[11px] font-medium leading-relaxed text-text-primary">{brief.summary}</p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {BRIEF_SECTIONS.filter((s) => brief[s.key]).map((s) => (
          <div key={s.key}>
            <div className="text-[10px] uppercase tracking-wider text-accent">{s.label}</div>
            <p className="text-[11px] leading-relaxed text-text-secondary">{brief[s.key]}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── One symbol card ─────────────────────────────────────────────── */

function DetailCard({
  it, onOpen, onRefresh, refreshing, isAdmin, onGenerate, generating,
}: {
  it: FundamentalsItem;
  onOpen: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  isAdmin: boolean;
  onGenerate: () => void;
  generating: boolean;
}) {
  const [showFull, setShowFull] = useState(false);
  const [showBrief, setShowBrief] = useState(false);
  const fetched = it.fetched_at != null;
  const desc = it.description ?? "";
  const long = desc.length > 220;

  return (
    <Card padding="md" className="space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <button onClick={onOpen} className="text-left">
          <div className="flex items-center gap-2">
            <span className="font-display text-base font-semibold text-text-primary">{it.symbol}</span>
            {it.consensus && (
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${consensusBadge(it.consensus)}`}>
                {it.consensus.toUpperCase()}
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
          Not fetched yet — tap Fetch to load fundamentals, analyst ratings, and metrics.
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

          {/* Key numbers — grouped + 2-col on mobile for readability */}
          <div className="rounded-lg border border-border-subtle/40 bg-surface-2/30 p-3 space-y-3">
            <div className="grid grid-cols-2 gap-x-3 gap-y-2.5 sm:grid-cols-4">
              <Stat label="EPS (ttm)" value={it.trailing_eps != null ? `$${it.trailing_eps.toFixed(2)}` : "—"} />
              <Stat label="EPS (fwd)" value={it.forward_eps != null ? `$${it.forward_eps.toFixed(2)}` : "—"} />
              <Stat
                label="EPS growth"
                value={it.eps_growth_pct != null ? `${it.eps_growth_pct > 0 ? "+" : ""}${it.eps_growth_pct.toFixed(1)}%` : "—"}
                color={growthColor(it.eps_growth_pct)}
              />
              <Stat label="P/E" value={it.pe_ratio != null ? it.pe_ratio.toFixed(1) : "—"} />
            </div>
            <MetricsRow it={it} />
          </div>

          {/* Analyst ratings */}
          <div className="space-y-1">
            <div className="text-[10px] uppercase tracking-wider text-text-faint">Analyst ratings</div>
            <RatingBar it={it} />
          </div>

          {/* AI investment brief — collapsed by default so the card stays scannable */}
          <div className="border-t border-border-subtle/40 pt-2">
            <div className="flex items-center justify-between">
              <button
                onClick={() => setShowBrief((v) => !v)}
                disabled={!it.ai_brief}
                className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-accent disabled:opacity-60"
              >
                {it.ai_brief && (showBrief ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />)}
                <Sparkles className="h-3 w-3" /> AI brief
                {it.ai_generated_at && (
                  <span className="text-text-faint normal-case tracking-normal">· {fmtRelativeAge(it.ai_generated_at)}</span>
                )}
                {it.ai_brief && !showBrief && <span className="text-text-faint normal-case tracking-normal">· tap to read</span>}
              </button>
              {isAdmin && (
                <button
                  onClick={onGenerate}
                  disabled={generating}
                  className="flex items-center gap-1 rounded-md bg-accent/15 px-2 py-0.5 text-[10px] font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-40"
                >
                  {generating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                  {it.ai_brief ? "Regenerate" : "Generate"}
                </button>
              )}
            </div>
            {it.ai_brief ? (
              showBrief && <div className="mt-2"><BriefView brief={it.ai_brief} /></div>
            ) : (
              <p className="mt-1 text-[11px] italic text-text-faint">
                {isAdmin
                  ? "No AI brief yet — tap Generate to write one (Sonnet)."
                  : "AI brief not generated yet — it'll appear here once it's run."}
              </p>
            )}
          </div>

          <div className="flex items-center justify-between text-[10px] text-text-faint">
            <span>Market cap {fmtMarketCap(it.market_cap)}</span>
            <span>Numbers updated {fmtRelativeAge(it.fetched_at)}</span>
          </div>
        </>
      )}
    </Card>
  );
}

/* ── Main tab ─────────────────────────────────────────────────────── */

export default function DetailsTab() {
  const [search, setSearch] = useState("");
  const { data, isLoading, error } = useWatchlistFundamentals();
  const refresh = useRefreshFundamentals();
  const aiGen = useGenerateAIBrief();
  const { data: me } = useMe();
  const isAdmin = (me?.email ?? "").trim().toLowerCase() === AI_ADMIN_EMAIL;
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
  const genAll = aiGen.isPending && aiGen.variables === undefined;
  const genSymbol = aiGen.isPending ? (aiGen.variables as string | undefined) : undefined;
  const q = search.trim().toLowerCase();
  const filtered = q ? items.filter((it) => it.symbol.toLowerCase().includes(q) || (it.company_name || "").toLowerCase().includes(q)) : items;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 text-xs text-text-faint">
        <span>Updated {fmtRelativeAge(data?.last_refreshed_at ?? null)}</span>
        <div className="flex items-center gap-2">
          {isAdmin && (
            <button
              onClick={() => aiGen.mutate(undefined)}
              disabled={aiGen.isPending}
              className="flex items-center gap-1.5 rounded-md bg-accent/15 px-2.5 py-1.5 text-[11px] font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-40 active:scale-95"
            >
              {genAll ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              Generate all briefs
            </button>
          )}
          <button
            onClick={() => refresh.mutate(undefined)}
            disabled={refresh.isPending}
            className="flex items-center gap-1.5 rounded-md bg-surface-3 px-2.5 py-1.5 text-[11px] font-medium text-text-secondary transition-colors hover:bg-surface-4 disabled:opacity-40 active:scale-95"
          >
            {refreshingAll ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh numbers
          </button>
        </div>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-faint" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search a stock…"
          className="w-full rounded-lg bg-surface-2 border border-border-subtle pl-9 pr-3 py-2 text-[12px] text-text-primary placeholder:text-text-faint focus:border-accent outline-none"
        />
      </div>

      {(refreshingAll || genAll) && (
        <p className="text-[10px] text-text-faint">
          {genAll
            ? "Generating AI briefs for all symbols — this can take a few minutes (Sonnet, one per symbol)."
            : "Refreshing all symbols — this can take a minute or two (throttled data)."}
        </p>
      )}

      {filtered.length === 0 ? (
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">No stocks match “{search}”.</div>
      ) : (
      <div className="space-y-3">
        {filtered.map(it => (
          <DetailCard
            key={it.symbol}
            it={it}
            onOpen={() => openSymbol(it.symbol)}
            onRefresh={() => refresh.mutate(it.symbol)}
            refreshing={refreshingAll || refreshingSymbol === it.symbol}
            isAdmin={isAdmin}
            onGenerate={() => aiGen.mutate(it.symbol)}
            generating={genAll || genSymbol === it.symbol}
          />
        ))}
      </div>
      )}
    </div>
  );
}
