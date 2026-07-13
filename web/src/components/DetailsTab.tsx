/** Research — the Watchlist page's master-detail research dossier.
 *
 *  Left: the watchlist symbols (grouped by sector) with a freshness dot + analyst
 *  rating. Right: the selected symbol's full dossier — key numbers, where it's
 *  trading (vs 50/200-day MA + 52-week range), the analyst street, and the
 *  AI-generated investment brief. All data from /fundamentals/watchlist; the brief
 *  + numbers refresh on demand. Nothing here is a trade plan — levels live on Trading.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useWatchlistFundamentals,
  useRefreshFundamentals,
  useGenerateAIBrief,
  useSymbolFundamentals,
  useEmerging,
  useGrowth,
  useMe,
  type FundamentalsItem,
} from "../api/hooks";
import { Skeleton } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import ResearchCard, {
  AI_ADMIN_EMAIL, consensusBadge, gradeBadge, freshDot, fmtAge,
} from "./ResearchCard";
import { Info, AlertCircle, Search } from "lucide-react";

/* ── Main master-detail tab ──────────────────────────────────────── */
export default function DetailsTab() {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const { data, isLoading, error } = useWatchlistFundamentals();
  const refresh = useRefreshFundamentals();
  const aiGen = useGenerateAIBrief();
  const { data: me } = useMe();
  const isAdmin = (me?.email ?? "").trim().toLowerCase() === AI_ADMIN_EMAIL;
  const navigate = useNavigate();
  const { data: em } = useEmerging();
  const { data: gr } = useGrowth();

  const items = data?.items ?? [];
  const q = search.trim().toLowerCase();
  const filtered = q ? items.filter((it) => it.symbol.toLowerCase().includes(q) || (it.company_name || "").toLowerCase().includes(q)) : items;

  // Group by sector, preserving encounter order.
  const groups = useMemo(() => {
    const g = new Map<string, FundamentalsItem[]>();
    filtered.forEach((it) => {
      const k = it.sector || "Other";
      let arr = g.get(k);
      if (!arr) { arr = []; g.set(k, arr); }
      arr.push(it);
    });
    return [...g.entries()];
  }, [filtered]);

  // Top-graded ideas from the discovery boards (Emerging + Growth), best grade first.
  const topIdeas = useMemo(() => {
    const rank = (g: string | null | undefined) => (g?.startsWith("A") ? 0 : g?.startsWith("B") ? 1 : g?.startsWith("C") ? 2 : 3);
    const map = new Map<string, { symbol: string; grade: string; score: number }>();
    const add = (sym: string, grade: string, score: number) => {
      const k = sym.toUpperCase();
      const cur = map.get(k);
      if (!cur || rank(grade) < rank(cur.grade) || (rank(grade) === rank(cur.grade) && score > cur.score)) map.set(k, { symbol: k, grade, score });
    };
    (em?.entries ?? []).forEach((e) => add(e.symbol, e.grade, e.score));
    (gr?.entries ?? []).forEach((e) => add(e.symbol, e.grade, e.score));
    return [...map.values()].sort((a, b) => rank(a.grade) - rank(b.grade) || b.score - a.score).slice(0, 10);
  }, [em, gr]);

  const activeSymbol = selected ?? filtered[0]?.symbol ?? topIdeas[0]?.symbol ?? null;
  const watchlistActive = items.find((it) => it.symbol === activeSymbol) ?? null;
  // A Top Idea that isn't on the watchlist → fetch its full dossier on demand.
  const needIdeaFetch = !watchlistActive && !!activeSymbol && topIdeas.some((t) => t.symbol === activeSymbol);
  const { data: ideaFund } = useSymbolFundamentals(needIdeaFetch ? activeSymbol : null);
  const active = watchlistActive ?? (needIdeaFetch ? ideaFund ?? null : null);

  if (isLoading) {
    return (
      <div className="flex gap-4" aria-busy="true">
        <div className="w-56 space-y-2"><Skeleton w={200} h={12} /><Skeleton w={200} h={200} /></div>
        <div className="flex-1"><Skeleton w={400} h={300} /></div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-1 p-4 text-bearish-text">
        <AlertCircle className="h-4 w-4" /><span className="text-sm">Failed to load research.</span>
      </div>
    );
  }
  if (items.length === 0 && topIdeas.length === 0) {
    return (
      <EmptyState
        icon={Info}
        title="No symbols to research yet"
        hint="Company fundamentals, analyst ratings, and AI briefs are pulled for the tickers on your watchlist. Add a few symbols and they'll appear here."
        primary={{ label: "Edit watchlist", to: "/watchlist" }}
      />
    );
  }

  const refreshingAll = refresh.isPending && refresh.variables === undefined;
  const refreshingSym = refresh.isPending ? (refresh.variables as string | undefined) : undefined;
  const genSym = aiGen.isPending ? (aiGen.variables as string | undefined) : undefined;

  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-start">
      {/* Master list */}
      <aside className="md:w-64 md:shrink-0 md:sticky md:top-2 space-y-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text-faint" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${items.length} names…`}
            className="w-full rounded-lg border border-border-subtle bg-surface-2 py-2 pl-8 pr-3 text-[12px] text-text-primary placeholder:text-text-faint outline-none focus:border-accent"
          />
        </div>
        <div className="max-h-[70vh] overflow-y-auto rounded-lg border border-border-subtle bg-surface-1">
          {/* ⭐ Top-graded ideas fed from the discovery boards — research them before adding */}
          {topIdeas.length > 0 && (
            <div>
              <div className="sticky top-0 z-10 bg-surface-1 px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider text-amber-400/80">⭐ Ideas · Top {topIdeas.length}</div>
              {topIdeas.map((t) => (
                <button
                  key={`idea-${t.symbol}`}
                  onClick={() => setSelected(t.symbol)}
                  className={`flex w-full items-center gap-2 border-l-2 px-2.5 py-1.5 text-left transition-colors ${
                    t.symbol === activeSymbol ? "border-accent bg-accent/[0.07]" : "border-transparent hover:bg-surface-2"
                  }`}
                >
                  <span className={`shrink-0 rounded px-1 py-0.5 text-[8.5px] font-bold ${gradeBadge(t.grade)}`}>{t.grade}</span>
                  <span className="flex-1 truncate font-mono text-[13px] font-bold text-text-primary">{t.symbol}</span>
                </button>
              ))}
            </div>
          )}
          {groups.map(([sector, rows]) => (
            <div key={sector}>
              <div className="sticky top-0 bg-surface-1 px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-wider text-amber-400/80">{sector}</div>
              {rows.map((it) => (
                <button
                  key={it.symbol}
                  onClick={() => setSelected(it.symbol)}
                  className={`flex w-full items-center gap-2 border-l-2 px-2.5 py-1.5 text-left transition-colors ${
                    it.symbol === activeSymbol ? "border-accent bg-accent/[0.07]" : "border-transparent hover:bg-surface-2"
                  }`}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${freshDot(it.fetched_at)}`} title={`Numbers ${fmtAge(it.fetched_at)}`} />
                  <span className="flex-1 truncate font-mono text-[13px] font-bold text-text-primary">{it.symbol}</span>
                  {it.consensus && <span className={`rounded px-1 py-0.5 text-[8.5px] font-bold ${consensusBadge(it.consensus)}`}>{it.consensus}</span>}
                </button>
              ))}
            </div>
          ))}
          {filtered.length === 0 && <p className="p-3 text-center text-[11px] text-text-faint">No match for “{search}”.</p>}
        </div>
        <p className="px-1 font-mono text-[9.5px] leading-relaxed text-text-faint">
          ● green = numbers ≤6h · ● amber = older · ○ not fetched. Numbers refresh nightly · briefs on demand.
        </p>
      </aside>

      {/* Detail dossier */}
      <div className="min-w-0 flex-1">
        {active ? (
          <ResearchCard
            it={active}
            isAdmin={isAdmin}
            onOpen={() => navigate(`/trading?symbol=${encodeURIComponent(active.symbol)}`)}
            onRefresh={() => refresh.mutate(active.symbol)}
            refreshing={refreshingAll || refreshingSym === active.symbol}
            onGenerate={() => aiGen.mutate(active.symbol)}
            generating={genSym === active.symbol}
          />
        ) : needIdeaFetch ? (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[12px] text-text-faint">Loading research for {activeSymbol}…</div>
        ) : (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[12px] text-text-faint">Pick a symbol to see its research.</div>
        )}
      </div>
    </div>
  );
}
