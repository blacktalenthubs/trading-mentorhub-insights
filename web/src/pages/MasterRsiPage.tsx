/** Master RSI — every symbol on the master watchlist with its daily RSI(14).
 *  The unfiltered companion to Today's Bottom Watch board (which only shows
 *  actionable oversold rows): here the whole master list is on one sortable
 *  table — RSI first-class, default order most-oversold first. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gauge, Info, Search } from "lucide-react";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import { useMasterRsi, type MasterRsiItem } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

function rsiClass(rsi: number | null): string {
  if (rsi == null) return "text-text-faint";
  if (rsi < 30) return "text-bullish-text";
  if (rsi <= 33) return "text-accent";
  if (rsi >= 70) return "text-bearish-text";
  return "text-text-primary";
}

function ZoneChip({ r }: { r: MasterRsiItem }) {
  if (r.rsi == null) return null;
  if (r.rsi < 30)
    return <span className="inline-flex items-center text-[10px] font-semibold text-bullish-text bg-bullish-subtle border border-bullish/30 px-1.5 py-0.5 rounded">Oversold</span>;
  if (r.rsi <= 33)
    return <span className="inline-flex items-center text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">Buy zone</span>;
  if (r.rsi >= 70)
    return <span className="inline-flex items-center text-[10px] font-semibold text-bearish-text bg-bearish-subtle border border-bearish/30 px-1.5 py-0.5 rounded">Overbought</span>;
  return null;
}

function delta(r: MasterRsiItem): number | null {
  return r.rsi != null && r.rsi_prev != null ? Math.round((r.rsi - r.rsi_prev) * 10) / 10 : null;
}

function DeltaCell({ r }: { r: MasterRsiItem }) {
  const d = delta(r);
  if (d == null) return <span className="font-mono text-text-faint">—</span>;
  const cls = d > 0 ? "text-bullish-text" : d < 0 ? "text-bearish-text" : "text-text-muted";
  return <span className={`font-mono ${cls}`}>{d > 0 ? "+" : ""}{d.toFixed(1)}</span>;
}

export default function MasterRsiPage() {
  const { data, isLoading, isError } = useMasterRsi();
  const { screenerPreviewRows } = useFeatureGate();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    const all = data ?? [];
    const needle = q.trim().toUpperCase();
    return needle ? all.filter((r) => r.symbol.includes(needle)) : all;
  }, [data, q]);

  const oversold = useMemo(() => (data ?? []).filter((r) => r.rsi != null && r.rsi <= 33).length, [data]);

  const columns: Column<MasterRsiItem>[] = [
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span><ZoneChip r={r} /></span>
    ) },
    { key: "rsi", label: "RSI (14)", align: "right", value: (r) => r.rsi ?? 999, render: (r) => (
      <span className={`font-mono font-bold ${rsiClass(r.rsi)}`}>{r.rsi != null ? r.rsi.toFixed(1) : "—"}</span>
    ) },
    { key: "delta", label: "Δ day", align: "right", cls: "hidden sm:table-cell", value: (r) => delta(r) ?? 999, render: (r) => <DeltaCell r={r} /> },
    { key: "close", label: "Close", align: "right", value: (r) => r.close ?? -1, render: (r) => (
      <span className="font-mono text-text-primary">{r.close != null ? `$${r.close.toFixed(2)}` : "—"}</span>
    ) },
    { key: "dist", label: "vs 200MA", align: "right", cls: "hidden lg:table-cell", value: (r) => r.dist_200ma_pct ?? -9999, render: (r) => (
      r.dist_200ma_pct == null
        ? <span className="font-mono text-text-faint">—</span>
        : <span className={`font-mono ${r.dist_200ma_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
            {r.dist_200ma_pct >= 0 ? "+" : ""}{r.dist_200ma_pct.toFixed(1)}%{r.near_200ma ? " · at 200" : ""}
          </span>
    ) },
  ];

  const mobileRow = (r: MasterRsiItem) => {
    const d = delta(r);
    return (
      <>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span><ZoneChip r={r} /></div>
          <span className={`font-mono text-sm font-bold ${rsiClass(r.rsi)}`}>{r.rsi != null ? r.rsi.toFixed(1) : "—"}</span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] text-text-muted font-mono">
          {r.close != null && <span>${r.close.toFixed(2)}</span>}
          {d != null && <span className={d > 0 ? "text-bullish-text" : d < 0 ? "text-bearish-text" : ""}>Δ {d > 0 ? "+" : ""}{d.toFixed(1)}</span>}
          {r.dist_200ma_pct != null && <span>200MA {r.dist_200ma_pct >= 0 ? "+" : ""}{r.dist_200ma_pct.toFixed(1)}%</span>}
        </div>
      </>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Gauge className="h-4 w-4 text-accent" /> Master RSI
            <span className="text-text-faint font-normal text-sm">· the full master watchlist by daily RSI</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">
            Daily RSI(14) for every name on the master watchlist. Bottom Watch shows only the oversold few — this is the whole board. Click any column header to sort.
          </p>
          <p className="text-[10px] text-text-faint/80 mt-1 flex items-center gap-1">
            <Info className="h-3 w-3 shrink-0" />
            Refreshes every 5 minutes. Intraday, the RSI reflects today's running close; after the bell it's the completed daily bar.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-text-faint">
            {(data ?? []).length} symbols{oversold > 0 && <> · <span className="text-bullish-text font-semibold">{oversold} at RSI ≤ 33</span></>}
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

      <ScreenerTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "rsi", dir: "asc" }}
        previewRows={screenerPreviewRows}
        previewLabel="master RSI rows"
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the master RSI board."
        empty={
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
              <Gauge className="h-6 w-6 text-text-faint" />
            </div>
            <p className="text-text-secondary font-medium">No symbols to show</p>
            <p className="text-text-faint text-sm mt-1">The master watchlist is empty, or no symbol matches your filter.</p>
          </div>
        }
      />
    </div>
  );
}
