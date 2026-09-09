/** Robinhood admin panel — on-demand trade import + read-only option chain.
 *  Rendered only for the owner account on the Daily Target page. No order
 *  placement: read-only import + option greeks lookup. */
import { useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { useRobinhoodImport, useOptionChain, type OptionRow } from "../api/hooks";

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
  const [exp, setExp] = useState("");
  const [otype, setOtype] = useState("both");
  const chainMut = useOptionChain();
  const rows: OptionRow[] = chainMut.data?.rows ?? [];

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
                {res.fills_seen} seen · {res.matched_trades} round-trips · realized P&amp;L on{" "}
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
              className={`${INPUT} w-24 uppercase`}
            />
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Expiration</span>
            <input type="date" value={exp} onChange={(e) => setExp(e.target.value)} className={INPUT} />
          </label>
          <label className="flex flex-col">
            <span className={LABEL}>Type</span>
            <select value={otype} onChange={(e) => setOtype(e.target.value)} className={INPUT}>
              <option value="both">Both</option>
              <option value="call">Calls</option>
              <option value="put">Puts</option>
            </select>
          </label>
          <button
            onClick={() => chainMut.mutate({ symbol: sym, exp, type: otype })}
            disabled={chainMut.isPending || !sym || !exp}
            className={BTN}
          >
            <Search size={14} />
            {chainMut.isPending ? "Loading…" : "Fetch chain"}
          </button>
        </div>
        {rows.length > 0 && (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead>
                <tr className="border-b border-border-subtle text-left text-text-faint">
                  <th className="py-1 pr-3">Type</th>
                  <th className="py-1 pr-3">Strike</th>
                  <th className="py-1 pr-3">Mark</th>
                  <th className="py-1 pr-3">Δ</th>
                  <th className="py-1 pr-3">Θ</th>
                  <th className="py-1 pr-3">IV</th>
                  <th className="py-1 pr-3">Vol</th>
                  <th className="py-1 pr-3">OI</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-border-subtle/50 text-text-secondary">
                    <td className="py-1 pr-3">{r.type}</td>
                    <td className="py-1 pr-3">{r.strike.toFixed(2)}</td>
                    <td className="py-1 pr-3">{r.mark.toFixed(2)}</td>
                    <td className="py-1 pr-3">{r.delta.toFixed(3)}</td>
                    <td className="py-1 pr-3">{r.theta.toFixed(3)}</td>
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
