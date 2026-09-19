/** Robinhood admin panel — on-demand trade import + read-only option chain.
 *  Rendered only for the owner account on the Daily Target page. No order
 *  placement: read-only import + option greeks lookup. */
import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import {
  useRobinhoodImport,
  useOptionChain,
  useOptionExpirations,
  type OptionRow,
} from "../api/hooks";

const COLS: { key: keyof OptionRow; label: string }[] = [
  { key: "type", label: "Type" },
  { key: "strike", label: "Strike" },
  { key: "mark", label: "Mark" },
  { key: "delta", label: "Δ Delta" },
  { key: "gamma", label: "Γ Gamma" },
  { key: "theta", label: "Θ Theta" },
  { key: "vega", label: "V Vega" },
  { key: "iv", label: "IV" },
  { key: "volume", label: "Vol" },
  { key: "open_interest", label: "OI" },
];

const INPUT =
  "mt-0.5 rounded-md bg-surface-2 border border-border-default px-2 py-1 text-[13px] text-text-primary focus:border-accent outline-none";
const LABEL = "text-[11px] uppercase tracking-wide text-text-faint";
const BTN =
  "inline-flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-50";
const CARD = "rounded-lg border border-border-subtle bg-surface-2/40 p-4";

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export function RobinhoodPanel() {
  const [impDate, setImpDate] = useState(todayISO());
  const [lookback, setLookback] = useState(3);
  const importMut = useRobinhoodImport();
  const res = importMut.data;

  const [sym, setSym] = useState("");
  const [symLoaded, setSymLoaded] = useState(""); // symbol whose expirations we've fetched
  const [exp, setExp] = useState("");
  const [otype, setOtype] = useState("both");
  const [near, setNear] = useState(10); // N nearest strikes each side of spot
  const expQuery = useOptionExpirations(symLoaded);
  const expirations = expQuery.data?.expirations ?? [];
  const chainMut = useOptionChain();

  // When a symbol's real expirations load, snap to the nearest one if the current
  // pick isn't a valid listed date (avoids the 0-contracts dead end).
  useEffect(() => {
    if (expirations.length && !expirations.includes(exp)) setExp(expirations[0]);
  }, [expirations, exp]);

  const loadExpirations = () => {
    const s = sym.trim().toUpperCase();
    if (s) setSymLoaded(s);
  };
  const rows: OptionRow[] = chainMut.data?.rows ?? [];

  const [sortKey, setSortKey] = useState<keyof OptionRow>("strike");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const sorted = useMemo(() => {
    const arr = [...rows];
    arr.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * sortDir;
      return String(av).localeCompare(String(bv)) * sortDir;
    });
    return arr;
  }, [rows, sortKey, sortDir]);
  const toggleSort = (k: keyof OptionRow) => {
    if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1));
    else { setSortKey(k); setSortDir(1); }
  };

  return (
    <div className="space-y-4">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-faint">
        Robinhood (read-only)
      </div>

      {/* ── Import trades ─────────────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-2 text-[13px] font-semibold text-text-primary">Import trades</div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col">
            <span className={LABEL}>Date</span>
            <input type="date" value={impDate} onChange={(e) => setImpDate(e.target.value)} className={INPUT} />
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Lookback (days)</span>
            <input
              type="number" min={0} max={90} value={lookback}
              onChange={(e) => setLookback(Number(e.target.value))}
              className={`${INPUT} w-24`}
            />
          </label>
          <button
            onClick={() => importMut.mutate({ date: impDate, lookback })}
            disabled={importMut.isPending}
            className={BTN}
          >
            <RefreshCw size={14} className={importMut.isPending ? "animate-spin" : ""} />
            {importMut.isPending ? "Importing…" : "Run import"}
          </button>
        </div>
        {res && (
          <div className="mt-3 text-[13px]">
            {res.error ? (
              <span className="text-red-500">Error: {res.error}</span>
            ) : res.skipped ? (
              <span className="text-amber-500">Skipped: {res.skipped}</span>
            ) : (
              <span className="text-text-secondary">
                Imported <b className="text-text-primary">{res.fills_imported}</b> new fill(s) ·{" "}
                {res.fills_seen} seen · {res.matched_trades} round-trips ·{" "}
                <b className="text-text-primary">{res.daily_target_rows}</b> journal rows · realized P&amp;L on{" "}
                {res.session_date}: <b className="text-text-primary">${res.realized_pnl.toFixed(2)}</b>
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Option chain + greeks ─────────────────────────────────── */}
      <div className={CARD}>
        <div className="mb-2 text-[13px] font-semibold text-text-primary">Option chain + greeks</div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col">
            <span className={LABEL}>Symbol</span>
            <input
              value={sym} placeholder="SPY"
              onChange={(e) => setSym(e.target.value.toUpperCase())}
              onBlur={loadExpirations}
              onKeyDown={(e) => { if (e.key === "Enter") loadExpirations(); }}
              className={`${INPUT} w-24 uppercase`}
            />
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Expiration</span>
            <select
              value={exp}
              onChange={(e) => setExp(e.target.value)}
              disabled={expQuery.isFetching || !expirations.length}
              className={`${INPUT} w-40`}
            >
              {expQuery.isFetching ? (
                <option value="">Loading…</option>
              ) : !symLoaded ? (
                <option value="">Enter a symbol first</option>
              ) : !expirations.length ? (
                <option value="">No expirations</option>
              ) : (
                expirations.map((d) => <option key={d} value={d}>{d}</option>)
              )}
            </select>
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Type</span>
            <select value={otype} onChange={(e) => setOtype(e.target.value)} className={INPUT}>
              <option value="both">Both</option>
              <option value="call">Calls</option>
              <option value="put">Puts</option>
            </select>
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Strikes ± (each side)</span>
            <input
              type="number" min={1} max={50} step={1} value={near}
              onChange={(e) => setNear(Math.max(1, Number(e.target.value)))}
              className={`${INPUT} w-20`}
            />
          </label>
          <button
            onClick={() => chainMut.mutate({ symbol: symLoaded || sym.trim().toUpperCase(), exp, type: otype, near })}
            disabled={chainMut.isPending || !exp}
            className={BTN}
          >
            <Search size={14} />
            {chainMut.isPending ? "Loading…" : "Fetch chain"}
          </button>
        </div>
        {chainMut.data && (
          <div className="mt-2 text-[12px] text-text-faint">
            {chainMut.data.symbol} underlying{" "}
            <b className="text-text-secondary">${chainMut.data.underlying_price.toFixed(2)}</b>
            {" · "}{near} strike{near === 1 ? "" : "s"} each side · {rows.length} contract{rows.length === 1 ? "" : "s"}
          </div>
        )}
        {rows.length > 0 && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead>
                <tr className="border-b border-border-subtle text-left text-text-faint">
                  {COLS.map((c) => (
                    <th
                      key={c.key}
                      onClick={() => toggleSort(c.key)}
                      className="cursor-pointer select-none py-1 pr-3 hover:text-text-secondary"
                    >
                      {c.label}
                      {sortKey === c.key ? (sortDir === 1 ? " ↑" : " ↓") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((r, i) => (
                  <tr
                    key={i}
                    className={`border-b border-border-subtle/50 ${
                      r.type === "call" ? "text-bullish-text" : r.type === "put" ? "text-bearish-text" : "text-text-secondary"
                    }`}
                  >
                    <td className="py-1 pr-3 capitalize">{r.type}</td>
                    <td className="py-1 pr-3 font-semibold text-text-primary">{r.strike.toFixed(2)}</td>
                    <td className="py-1 pr-3">{r.mark.toFixed(2)}</td>
                    <td className="py-1 pr-3">{r.delta.toFixed(3)}</td>
                    <td className="py-1 pr-3">{r.gamma.toFixed(4)}</td>
                    <td className="py-1 pr-3">{r.theta.toFixed(3)}</td>
                    <td className="py-1 pr-3">{r.vega.toFixed(3)}</td>
                    <td className="py-1 pr-3">{(r.iv * 100).toFixed(1)}%</td>
                    <td className="py-1 pr-3">{r.volume.toFixed(0)}</td>
                    <td className="py-1 pr-3">{r.open_interest.toFixed(0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
