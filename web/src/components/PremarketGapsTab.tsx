/** Premarket Gap Board — stocks gapping pre-bell so you can plan before the open.
 *  A sortable table: gap%, price, premarket $-volume (liquidity), market cap,
 *  sector, and key levels (PMH/PDH/PDL) — the data that tells you WHY to trade it.
 *  Gated to stable ≥$3B names; AI/tech space is surfaced first and filterable.
 *  Click a header to sort, a row to chart it, + to add to your watchlist.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  usePremarketGaps,
  useRefreshPremarketGaps,
  useWatchlist,
  useAddSymbol,
  type PremarketGapEntry,
} from "../api/hooks";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import { Activity, RefreshCw, Plus, Check, Cpu, ArrowUp, ArrowDown, Newspaper } from "lucide-react";

type SortKey = "gap" | "vol" | "mktcap" | "price" | "symbol";

function fmtAge(iso: string | null): string {
  if (!iso) return "never";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`;
}
function gapColor(g: number | null): string {
  if (g == null) return "text-text-faint";
  return g > 0 ? "text-bullish-text" : "text-bearish-text";
}
function fmtGap(g: number | null): string {
  return g == null ? "—" : `${g > 0 ? "+" : ""}${g.toFixed(1)}%`;
}
function fmtVol(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}
function fmtMktCap(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}
function fmtPx(v: number | null): string {
  return v == null ? "—" : `$${v.toFixed(2)}`;
}

function Th({ label, active, dir, align, onClick }: {
  label: string; active: boolean; dir: "asc" | "desc"; align?: "right"; onClick: () => void;
}) {
  return (
    <th
      onClick={onClick}
      className={`px-3 py-2 font-semibold cursor-pointer select-none hover:text-text-secondary ${align === "right" ? "text-right" : "text-left"}`}
    >
      <span className={`inline-flex items-center gap-0.5 ${align === "right" ? "flex-row-reverse" : ""}`}>
        {label}
        {active && (dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
      </span>
    </th>
  );
}

function GapTableRow({ e, owned, onChart, onAdd, adding }: {
  e: PremarketGapEntry; owned: boolean; onChart: () => void; onAdd: () => void; adding: boolean;
}) {
  return (
    <tr className="border-b border-border-subtle/30 last:border-b-0 hover:bg-surface-2/40">
      {/* Symbol + AI badge + catalyst */}
      <td className="px-3 py-2 align-top">
        <button onClick={onChart} className="text-left" title={`Chart ${e.symbol}`}>
          <span className="flex items-center gap-1.5">
            <span className="font-semibold text-text-primary">{e.symbol}</span>
            {e.is_ai && (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-accent bg-accent/10 px-1 py-0.5 rounded" title="AI / tech space">
                <Cpu className="h-2.5 w-2.5" /> AI
              </span>
            )}
          </span>
          {e.catalyst && (
            <span className="mt-0.5 flex items-start gap-1 text-[10px] text-text-muted max-w-[220px]">
              <Newspaper className="h-2.5 w-2.5 mt-0.5 shrink-0 text-accent/70" />
              <span className="line-clamp-1">{e.catalyst}</span>
            </span>
          )}
        </button>
      </td>
      <td className={`px-3 py-2 text-right font-mono font-bold whitespace-nowrap ${gapColor(e.gap_pct)}`}>{fmtGap(e.gap_pct)}</td>
      <td className="px-3 py-2 text-right font-mono text-text-secondary whitespace-nowrap">{fmtPx(e.pm_last)}</td>
      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap" title="Premarket $-volume (liquidity)">{fmtVol(e.pm_dollar_vol)}</td>
      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{fmtMktCap(e.market_cap)}</td>
      <td className="px-3 py-2 text-text-muted text-xs max-w-[130px] truncate" title={e.sector ?? ""}>{e.sector ?? "—"}</td>
      <td className="px-3 py-2 text-right font-mono text-[10px] text-text-faint whitespace-nowrap">
        <span title="Premarket high">PMH {fmtPx(e.pm_high)}</span>{" · "}
        <span title="Prior day high">{fmtPx(e.pdh)}</span>/<span title="Prior day low">{fmtPx(e.pdl)}</span>
      </td>
      <td className="px-2 py-2 text-center">
        {owned ? (
          <span className="inline-flex items-center text-bullish-text" title="On your watchlist"><Check className="h-4 w-4" /></span>
        ) : (
          <button onClick={onAdd} disabled={adding}
            className="p-1 rounded text-accent hover:bg-accent/10 disabled:opacity-50 active:scale-95"
            title={`Add ${e.symbol} to watchlist`}>
            <Plus className="h-4 w-4" />
          </button>
        )}
      </td>
    </tr>
  );
}

export default function PremarketGapsTab() {
  const { data, isLoading, error } = usePremarketGaps();
  const refresh = useRefreshPremarketGaps();
  const { data: watchlist } = useWatchlist();
  const addSymbol = useAddSymbol();
  const navigate = useNavigate();

  const [sortKey, setSortKey] = useState<SortKey>("gap");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [aiOnly, setAiOnly] = useState(false);

  const watchSet = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );

  const entries = data?.entries ?? [];
  const aiCount = useMemo(() => entries.filter((e) => e.is_ai).length, [entries]);

  const rows = useMemo(() => {
    const r = (aiOnly ? entries.filter((e) => e.is_ai) : entries.slice());
    const dir = sortDir === "asc" ? 1 : -1;
    const num = (e: PremarketGapEntry): number => {
      switch (sortKey) {
        case "gap": return Math.abs(e.gap_pct ?? 0);
        case "vol": return e.pm_dollar_vol ?? 0;
        case "mktcap": return e.market_cap ?? 0;
        case "price": return e.pm_last ?? 0;
        default: return 0;
      }
    };
    r.sort((a, b) =>
      sortKey === "symbol" ? dir * a.symbol.localeCompare(b.symbol) : dir * (num(a) - num(b)),
    );
    return r;
  }, [entries, sortKey, sortDir, aiOnly]);

  function toggleSort(k: SortKey) {
    if (sortKey === k) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" ? "asc" : "desc"); }
  }
  function onChart(s: string) { navigate(`/trading?symbol=${encodeURIComponent(s)}`); }

  if (isLoading) {
    return <div className="space-y-3"><Skeleton w={200} h={16} /><SkeletonRow count={6} h={44} /></div>;
  }
  if (error) {
    return <div className="text-center py-12 text-sm text-bearish-text">Failed to load premarket gaps.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 text-xs text-text-faint flex-wrap">
        <span>
          {rows.length} gappers · gap ≥ 2% · ≥ $3B cap
          {data?.captured_at && <> · {fmtAge(data.captured_at)}{data.stale && " · stale"}</>}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAiOnly((v) => !v)}
            className={`flex items-center gap-1 rounded-full px-2.5 py-1.5 transition-colors ${aiOnly ? "bg-accent text-white" : "bg-accent/15 text-accent hover:bg-accent/25"}`}
            title="Show only AI / tech-space names"
          >
            <Cpu className="h-3.5 w-3.5" /> {aiOnly ? "AI only" : `AI (${aiCount})`}
          </button>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="flex items-center gap-1.5 rounded-full bg-accent/15 text-accent px-3 py-1.5 hover:bg-accent/25 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Scanning…" : "Scan now"}
          </button>
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title={aiOnly ? "No AI-space gappers right now" : "No premarket gappers yet"}
          hint="The scan runs every 15 min from 7:00–9:45 AM ET and lists ≥$3B stocks gapping with real premarket volume. Outside that window it'll be empty — or tap 'Scan now'."
        />
      ) : (
        <div className="overflow-x-auto bg-surface-1 border border-border-subtle rounded-xl">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-text-faint border-b border-border-subtle">
                <Th label="Symbol" active={sortKey === "symbol"} dir={sortDir} onClick={() => toggleSort("symbol")} />
                <Th label="Gap %" active={sortKey === "gap"} dir={sortDir} align="right" onClick={() => toggleSort("gap")} />
                <Th label="Price" active={sortKey === "price"} dir={sortDir} align="right" onClick={() => toggleSort("price")} />
                <Th label="PM Vol" active={sortKey === "vol"} dir={sortDir} align="right" onClick={() => toggleSort("vol")} />
                <Th label="Mkt Cap" active={sortKey === "mktcap"} dir={sortDir} align="right" onClick={() => toggleSort("mktcap")} />
                <th className="px-3 py-2 text-left font-semibold">Sector</th>
                <th className="px-3 py-2 text-right font-semibold">Levels</th>
                <th className="px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <GapTableRow key={e.symbol} e={e} owned={watchSet.has(e.symbol.toUpperCase())}
                  onChart={() => onChart(e.symbol)} onAdd={() => addSymbol.mutate(e.symbol)} adding={addSymbol.isPending} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[11px] text-text-faint leading-relaxed">
        Sorted <span className="text-text-secondary">AI-space first</span> by default — tap any header to re-sort.
        Gap % is premarket vs prior close; <span className="text-text-secondary">PM Vol</span> is premarket $-volume (liquidity);
        <span className="text-text-secondary"> Levels</span> = premarket high · prior-day high/low (your plan levels).
        Board is gated to stable <span className="text-text-secondary">≥ $3B</span> names.
      </p>
    </div>
  );
}
