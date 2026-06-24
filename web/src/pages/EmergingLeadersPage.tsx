/** Emerging Leaders — the weekly themed discovery scout under Trade Ideas (#64-O).
 *  Finds names STARTING to move inside the user's sectors (next MU/SNDK at the base):
 *  Stage 1→2 turn · RS vs SPY · volume surge · sector tailwind — a transparent ✓/✗.
 *  A scout card is DISCOVERY, not an entry (no entry/stop) — one tap adds it to the
 *  watchlist, which is what unlocks its alerts. Mounts as a Trade Ideas tab. */

import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Compass, RefreshCw } from "lucide-react";
import { useEmerging, useRefreshEmerging, useWatchlist, useAddSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import type { EmergingEntry } from "./InPlay.types";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

// The four emergence conditions, in display order. Maps scorecard keys → short labels.
const CRITERIA: { key: string; label: string }[] = [
  { key: "stage_turn", label: "Stage" },
  { key: "rs_leadership", label: "RS" },
  { key: "vol_surge", label: "Vol" },
  { key: "sector_tailwind", label: "Sector" },
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

export function EmergingTabView() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useEmerging();
  const refresh = useRefreshEmerging();
  const { isPro } = useFeatureGate();

  const { data: watchlist } = useWatchlist();
  const addSym = useAddSymbol();
  const owned = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );

  const rows = data?.entries ?? [];
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const AddCell = ({ r }: { r: EmergingEntry }) =>
    owned.has(r.symbol.toUpperCase()) ? (
      <span className="text-[11px] text-text-faint">✓ on watchlist</span>
    ) : (
      <button
        onClick={(e) => { e.stopPropagation(); addSym.mutate(r.symbol); }}
        className="text-[11px] font-semibold text-accent hover:text-accent-hover"
      >
        + watchlist
      </button>
    );

  const columns: Column<EmergingEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-8", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={`Emerging ${r.grade} — score ${r.score}/100`} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2">
        <span className="font-bold text-text-primary">{r.symbol}</span>
        <span className="text-[10px] text-text-faint">{r.sector}</span>
      </span>
    ) },
    { key: "why", label: "Why now", align: "left", cls: "max-w-[260px]", value: (r) => r.score, render: (r) => <span className="text-text-secondary text-xs">{r.why}</span> },
    { key: "scorecard", label: "Scorecard", align: "left", value: (r) => r.score, render: (r) => <Scorecard sc={r.scorecard} /> },
    { key: "vol", label: "Vol×", align: "right", cls: "hidden lg:table-cell", value: (r) => r.vol_surge ?? 0, render: (r) => r.vol_surge == null ? <span className="text-text-faint">—</span> : <span className={`font-mono ${r.vol_surge >= 1.5 ? "text-bullish-text" : "text-text-secondary"}`}>{r.vol_surge.toFixed(1)}×</span> },
    { key: "rs", label: "RS vs SPY", align: "right", cls: "hidden lg:table-cell", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "price", label: "Price", align: "right", cls: "hidden sm:table-cell", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "add", label: "", align: "right", cls: "w-28", render: (r) => <AddCell r={r} /> },
  ];

  const mobileRow = (r: EmergingEntry) => (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2">
          <span className="font-mono text-text-faint text-xs">{r.rank}</span>
          <span className="font-bold text-text-primary">{r.symbol}</span>
          <span className="text-[10px] text-text-faint">{r.sector}</span>
          <GradeBadge grade={r.grade} title={`Score ${r.score}/100`} />
        </span>
        <span className="font-mono text-sm text-text-primary">{money(r.last_price)}</span>
      </div>
      <p className="text-xs text-text-secondary">{r.why}</p>
      <Scorecard sc={r.scorecard} />
      <div className="flex items-center justify-between pt-0.5">
        <span className="flex items-center gap-3 text-[10px] text-text-muted">
          {r.vol_surge != null && <span>{r.vol_surge.toFixed(1)}× vol</span>}
          <span>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
        </span>
        <AddCell r={r} />
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <Compass className="h-5 w-5 text-sky-400" />
          <div>
            <h1 className="text-lg font-bold text-text-primary">Emerging — in your themes</h1>
            <p className="text-[11px] text-text-muted">
              Names starting to move inside the sectors you trade — the next leader at the base. Each scores Stage 1→2 turn · RS · volume surge · sector tailwind. Add one to your watchlist and it starts throwing your alerts.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {captured && <span className="text-text-faint">Updated {captured.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
          {isPro && (
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-sky-400/15 text-sky-400 hover:bg-sky-400/25 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
              {refresh.isPending ? "Scanning…" : "Run scan"}
            </button>
          )}
        </div>
      </div>

      <ScreenerTable<EmergingEntry>
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "scorecard", dir: "desc" }}
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the Emerging board."
        empty={
          <div className="px-4 py-10 text-center text-sm text-text-muted">
            No emerging names in the latest run.
            {isPro && " Tap Run scan to refresh."}
          </div>
        }
      />
    </div>
  );
}
