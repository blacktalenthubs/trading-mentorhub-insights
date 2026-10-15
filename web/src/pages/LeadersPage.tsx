/** Leaders — ONLY the master-watchlist symbols that currently hold leader
 *  status: close above the RISING weekly SMA20 and SMA50 (completed weeks).
 *  The weekly chart grants the badge; the daily chart sets the state —
 *  At Average is the buy zone, Slipping is under the daily 20, Extended is
 *  stretched, Broken is under the daily 50. Computed from completed bars
 *  only, so the board updates once daily after the close; non-leaders are
 *  counted in the header but never listed. Click a row for its chart. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Crown, Info, Search } from "lucide-react";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import { useLeaders, type LeaderItem } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

const STATE_ORDER: Record<string, number> = { AT_AVERAGE: 0, SLIPPING: 1, EXTENDED: 2, BROKEN: 3 };
const STATE_LABEL: Record<string, string> = {
  AT_AVERAGE: "At average",
  SLIPPING: "Slipping",
  EXTENDED: "Extended",
  BROKEN: "Broken",
};

function stateChipClass(state: string | null): string {
  switch (state) {
    case "AT_AVERAGE":
      return "text-bullish-text bg-bullish-subtle border-bullish/30";
    case "SLIPPING":
      return "text-accent bg-accent/10 border-accent/20";
    case "BROKEN":
      return "text-bearish-text bg-bearish-subtle border-bearish/30";
    default:
      return "text-text-muted bg-surface-2 border-border-subtle";
  }
}

function StateChip({ state }: { state: string | null }) {
  if (!state) return null;
  return (
    <span className={`inline-flex items-center text-[10px] font-semibold border px-1.5 py-0.5 rounded ${stateChipClass(state)}`}>
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

function money(v: number | null): string {
  return v != null ? `$${v.toFixed(2)}` : "—";
}

function pctOf(close: number | null, avg: number | null): number | null {
  return close != null && avg != null && avg !== 0 ? ((close - avg) / avg) * 100 : null;
}

function pctText(close: number | null, avg: number | null): string | null {
  const p = pctOf(close, avg);
  return p == null ? null : `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`;
}

/** An average's value with the close's signed distance from it — green when
 *  price sits above the average, red when below — so where a name stands
 *  against each daily/weekly SMA reads at a glance, no mental math. */
function avgCell(close: number | null, v: number | null) {
  if (v == null) return <span className="font-mono text-text-faint">—</span>;
  const p = pctOf(close, v);
  return (
    <span className="font-mono text-text-secondary">
      {money(v)}
      {p != null && (
        <span className={`ml-1.5 text-[10px] font-semibold ${p >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
          {p >= 0 ? "+" : ""}{p.toFixed(1)}%
        </span>
      )}
    </span>
  );
}

const FILTERS: { key: string; label: string }[] = [
  { key: "ALL", label: "All states" },
  { key: "AT_AVERAGE", label: "At average" },
  { key: "SLIPPING", label: "Slipping" },
  { key: "EXTENDED", label: "Extended" },
  { key: "BROKEN", label: "Broken" },
];

export default function LeadersPage() {
  const { data, isLoading, isError } = useLeaders();
  const { screenerPreviewRows } = useFeatureGate();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [f, setF] = useState("ALL");

  const all = data?.rows ?? [];
  const stateCounts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const r of all) if (r.state) m[r.state] = (m[r.state] ?? 0) + 1;
    return m;
  }, [all]);

  const rows = useMemo(() => {
    const needle = q.trim().toUpperCase();
    return all.filter(
      (r) => (f === "ALL" || r.state === f) && (!needle || r.symbol.includes(needle)),
    );
  }, [all, q, f]);

  const columns: Column<LeaderItem>[] = [
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="font-bold text-text-primary">{r.symbol}</span>
    ) },
    { key: "state", label: "State", align: "left", value: (r) => STATE_ORDER[r.state ?? ""] ?? 9, render: (r) => <StateChip state={r.state} /> },
    { key: "close", label: "Close", align: "right", value: (r) => r.close ?? -1, render: (r) => (
      <span className="font-mono text-text-primary">{money(r.close)}</span>
    ) },
    { key: "d20", label: "Daily 20", align: "right", value: (r) => pctOf(r.close, r.d20) ?? -999, render: (r) => avgCell(r.close, r.d20) },
    { key: "d50", label: "Daily 50", align: "right", cls: "hidden md:table-cell", value: (r) => pctOf(r.close, r.d50) ?? -999, render: (r) => avgCell(r.close, r.d50) },
    { key: "w20", label: "Weekly 20", align: "right", cls: "hidden lg:table-cell", value: (r) => pctOf(r.close, r.w20) ?? -999, render: (r) => avgCell(r.close, r.w20) },
    { key: "w50", label: "Weekly 50", align: "right", cls: "hidden lg:table-cell", value: (r) => pctOf(r.close, r.w50) ?? -999, render: (r) => avgCell(r.close, r.w50) },
    { key: "rsi", label: "RSI (14)", align: "right", value: (r) => r.rsi ?? -1, render: (r) => (
      <span className="font-mono text-text-primary">{r.rsi != null ? r.rsi.toFixed(1) : "—"}</span>
    ) },
  ];

  const mobileRow = (r: LeaderItem) => (
    <>
      <div className="flex items-center justify-between">
        <span className="font-bold text-text-primary">{r.symbol}</span>
        <StateChip state={r.state} />
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] text-text-muted font-mono">
        {r.close != null && <span>${r.close.toFixed(2)}</span>}
        {r.d20 != null && <span>D20 {pctText(r.close, r.d20)}</span>}
        {r.d50 != null && <span>D50 {pctText(r.close, r.d50)}</span>}
        {r.w20 != null && <span>W20 {pctText(r.close, r.w20)}</span>}
        {r.w50 != null && <span>W50 {pctText(r.close, r.w50)}</span>}
        {r.rsi != null && <span>RSI {r.rsi.toFixed(1)}</span>}
      </div>
    </>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Crown className="h-4 w-4 text-accent" /> Leaders
            <span className="text-text-faint font-normal text-sm">· master watchlist names holding leader status</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">
            A leader closes above its rising weekly 20 and 50 SMA — nothing else is listed. At Average is the buy zone;
            Broken means under the daily 50, no trade until reclaimed.
          </p>
          <p className="text-[10px] text-text-faint/80 mt-1 flex items-center gap-1">
            <Info className="h-3 w-3 shrink-0" />
            Completed bars only — the board updates once daily after the close
            {data?.as_of && <> · as of {data.as_of} close</>}. The % beside each average is how far the
            close sits above (+) or below (−) it — green above, red below.
            {data && data.counts.probation > 0 && <> {data.counts.probation} more on probation (over the weekly 50, badge at risk).</>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-text-faint">
            <span className="text-text-primary font-semibold">{data?.counts.leaders ?? 0} leaders</span>
            {data && <> of {data.universe} master symbols</>}
          </span>
          <label className="flex items-center gap-1.5 bg-surface-1 border border-border-subtle rounded px-2 py-1">
            <Search className="h-3.5 w-3.5 text-text-muted" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Filter symbol…"
              className="bg-transparent outline-none text-xs text-text-secondary w-28 placeholder:text-text-faint"
            />
          </label>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((x) => {
          const n = x.key === "ALL" ? all.length : (stateCounts[x.key] ?? 0);
          const active = f === x.key;
          return (
            <button
              key={x.key}
              onClick={() => setF(x.key)}
              className={`text-[11px] font-medium border rounded px-2 py-1 ${active ? "text-accent bg-accent/10 border-accent/30" : "text-text-muted bg-surface-1 border-border-subtle"}`}
            >
              {x.label} · {n}
            </button>
          );
        })}
      </div>

      <ScreenerTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "state", dir: "asc" }}
        previewRows={screenerPreviewRows}
        previewLabel="leader rows"
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the leaders board."
        empty={
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
              <Crown className="h-6 w-6 text-text-faint" />
            </div>
            <p className="text-text-secondary font-medium">No current leaders to show</p>
            <p className="text-text-faint text-sm mt-1">
              {all.length === 0
                ? "No master symbol currently closes above its rising weekly 20 and 50. The board repopulates as names earn the badge back."
                : "No leader matches your filter."}
            </p>
          </div>
        }
      />
    </div>
  );
}
