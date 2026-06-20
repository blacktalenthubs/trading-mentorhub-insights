/** Growth Leaders — the "Long Term" board under Trade Ideas (#64-M).
 *  Ranks the curated growth-leader universe on the Mathematical Growth-Stock
 *  Framework (fundamental + technical leadership) with a transparent ✓/✗ scorecard.
 *  Exported as GrowthLeadersTabView so it mounts as a Trade Ideas tab. */

import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { TrendingUp, RefreshCw } from "lucide-react";
import { useGrowth, useRefreshGrowth, useWatchlist, useAddSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import type { GrowthEntry } from "./InPlay.types";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

// The framework criteria, in display order. Maps the scorecard keys → short labels.
const CRITERIA: { key: string; label: string }[] = [
  { key: "rev_growth", label: "Rev" },
  { key: "earnings", label: "EPS" },
  { key: "gross_margin", label: "Margin" },
  { key: "stage2", label: "Stage2" },
  { key: "rs_leadership", label: "RS" },
  { key: "near_52wh", label: "52wH" },
  { key: "institutional", label: "Inst" },
];

function Scorecard({ sc }: { sc: Record<string, string> }) {
  return (
    <span className="flex flex-wrap gap-1">
      {CRITERIA.map((c) => {
        const st = sc?.[c.key] ?? "pending";
        const cls =
          st === "pass" ? "bg-bullish-text/15 text-bullish-text"
          : st === "fail" ? "bg-bearish-text/15 text-bearish-text"
          : "bg-surface-3 text-text-faint";
        const mark = st === "pass" ? "✓" : st === "fail" ? "✗" : "–";
        return (
          <span key={c.key} className={`text-[9px] font-semibold px-1 py-0.5 rounded ${cls}`} title={`${c.label}: ${st}`}>
            {c.label} {mark}
          </span>
        );
      })}
    </span>
  );
}

export function GrowthLeadersTabView() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useGrowth();
  const refresh = useRefreshGrowth();
  const { isPro } = useFeatureGate();

  const { data: watchlist } = useWatchlist();
  const addSym = useAddSymbol();
  const owned = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );

  const rows = data?.entries ?? [];
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const columns: Column<GrowthEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-8", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={`Growth Leader ${r.grade} — score ${r.score}/100`} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2">
        <span className="font-bold text-text-primary">{r.symbol}</span>
        {r.sector && <span className="text-[10px] text-text-faint">{r.sector}</span>}
      </span>
    ) },
    { key: "price", label: "Price", align: "right", cls: "hidden sm:table-cell", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "scorecard", label: "Scorecard", align: "left", value: (r) => r.score, render: (r) => <Scorecard sc={r.scorecard} /> },
    { key: "rs", label: "RS vs SPY", align: "right", cls: "hidden lg:table-cell", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "off52", label: "% off 52wH", align: "right", cls: "hidden xl:table-cell", value: (r) => r.pct_off_52wh ?? 999, render: (r) => r.pct_off_52wh == null ? <span className="text-text-faint">—</span> : <span className={`font-mono ${r.pct_off_52wh <= 10 ? "text-bullish-text" : "text-text-secondary"}`}>-{r.pct_off_52wh.toFixed(1)}%</span> },
    { key: "score", label: "Score", align: "right", cls: "w-12", value: (r) => r.score, render: (r) => <span className="font-mono font-bold text-text-primary">{r.score}</span> },
  ];

  const mobileRow = (r: GrowthEntry) => (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span className="font-mono text-text-faint text-xs">{r.rank}</span>
          <span className="font-bold text-text-primary">{r.symbol}</span>
          <GradeBadge grade={r.grade} title={`Score ${r.score}/100`} />
        </span>
        <span className="font-mono text-sm text-text-primary">{money(r.last_price)}</span>
      </div>
      <Scorecard sc={r.scorecard} />
      <div className="flex items-center gap-3 text-[10px] text-text-muted">
        <span>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
        {r.pct_off_52wh != null && <span>-{r.pct_off_52wh.toFixed(1)}% off 52wH</span>}
        {owned.has(r.symbol.toUpperCase()) ? <span className="text-text-faint">on watchlist</span>
          : <button onClick={(e) => { e.stopPropagation(); addSym.mutate(r.symbol); }} className="text-accent">+ watchlist</button>}
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-emerald-400" />
          <div>
            <h1 className="text-lg font-bold text-text-primary">Long Term — Growth Leaders</h1>
            <p className="text-[11px] text-text-muted">
              The proven growth leaders by the Mathematical Growth-Stock Framework — fundamentals × relative-strength leadership. Each name shows its ✓/✗ scorecard. Pair with the weekly chart (WkPos) to time the entry.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {captured && <span className="text-text-faint">Updated {captured.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
          {isPro && (
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-400/15 text-emerald-400 hover:bg-emerald-400/25 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
              {refresh.isPending ? "Scanning…" : "Run scan"}
            </button>
          )}
        </div>
      </div>

      <ScreenerTable<GrowthEntry>
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "score", dir: "desc" }}
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the Growth Leaders board."
        empty={
          <div className="px-4 py-10 text-center text-sm text-text-muted">
            No Growth Leaders in the latest run.
            {isPro && " Tap Run scan to refresh."}
          </div>
        }
      />
    </div>
  );
}
