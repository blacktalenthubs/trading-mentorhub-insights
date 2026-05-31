/** Swing screener (spec 62 follow-up) — market-wide DAILY-bar setups.
 *  Trend + 21/50 EMA defense, ranked by relative strength. Not market-gated:
 *  daily bars are valid all week (incl. weekends). Uses the shared ScreenerTable.
 */

import { useNavigate } from "react-router-dom";
import { TrendingUp, RefreshCw, Zap, Moon } from "lucide-react";
import { useSwingScreener, useRefreshSwing } from "../api/hooks";
import ScreenerTable, { type Column } from "./ScreenerTable";
import type { SwingEntry } from "../pages/InPlay.types";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

function Pct({ v }: { v: number }) {
  const up = v >= 0;
  return <span className={`font-mono ${up ? "text-bullish-text" : "text-bearish-text"}`}>{up ? "+" : ""}{v.toFixed(1)}%</span>;
}

function Conv({ c }: { c: string }) {
  const cls = c === "High" ? "text-bullish-text bg-bullish/10" : "text-amber-400 bg-amber-400/10";
  return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cls}`}>{c}</span>;
}

export default function SwingScreenerView() {
  const { data, isLoading, isError } = useSwingScreener();
  const refresh = useRefreshSwing();
  const navigate = useNavigate();

  const rows = data?.entries ?? [];
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const columns: Column<SwingEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-10", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span>
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded"><Zap className="h-3 w-3" />{r.setup?.pattern ?? "EMA Defense"}</span></span>
    ) },
    { key: "price", label: "Price", align: "right", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "ret_20d", label: "20d", align: "right", cls: "hidden lg:table-cell", value: (r) => r.ret_20d, render: (r) => <Pct v={r.ret_20d} /> },
    { key: "rs", label: "RS vs SPY", align: "right", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "entry", label: "Entry", align: "right", render: (r) => <span className="font-mono text-text-primary">{money(r.setup?.entry)}</span> },
    { key: "stop", label: "Stop", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bearish-text">{money(r.setup?.stop)}</span> },
    { key: "target", label: "Target", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bullish-text">{money(r.setup?.target)}</span> },
    { key: "conviction", label: "Conviction", align: "left", render: (r) => (r.setup ? <Conv c={r.setup.conviction} /> : null) },
  ];

  const mobileRow = (r: SwingEntry) => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span>{r.setup && <Conv c={r.setup.conviction} />}</div>
        <span className="font-mono text-sm text-text-primary">{money(r.setup?.entry)}</span>
      </div>
      <div className="flex gap-3 mt-1 text-[11px] text-text-muted font-mono">
        <span>20d <Pct v={r.ret_20d} /></span><span>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
        <span>S {money(r.setup?.stop)}</span><span>T {money(r.setup?.target)}</span>
      </div>
    </>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-accent" /> Swing setups
            <span className="text-text-faint font-normal text-sm">· trend + 21/50 EMA defense</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">
            Scans the whole market on daily bars for stocks defending key MAs with relative strength — valid all week.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-text-faint inline-flex items-center gap-1.5">
            {captured ? <>as of {captured.toLocaleDateString([], { month: "short", day: "numeric" })}</> : <><Moon className="h-3 w-3" /> not scanned yet</>}
            {rows.length > 0 && <span>· {rows.length} setups</span>}
          </span>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="text-xs px-3 py-1.5 rounded-lg bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center gap-1.5"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Scanning…" : "Run scan"}
          </button>
        </div>
      </div>

      <ScreenerTable
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "rs", dir: "desc" }}
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load swing setups."
        empty={
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
              <TrendingUp className="h-6 w-6 text-text-faint" />
            </div>
            <p className="text-text-secondary font-medium">No swing setups qualify right now</p>
            <p className="text-text-faint text-sm mt-1">Run a scan to check the market for trend + EMA-defense setups.</p>
          </div>
        }
      />
    </div>
  );
}
