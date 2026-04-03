import { useState, useMemo } from "react";
import { useTradeHistory } from "../api/hooks";
import { SkeletonTable } from "../components/LoadingSkeleton";
import CalendarHeatmap from "../components/CalendarHeatmap";

type Tab = "list" | "calendar" | "stop-discipline" | "symbol-lookup";

export default function HistoryPage() {
  const { data: trades, isLoading } = useTradeHistory();
  const [filter, setFilter] = useState("");
  const [tab, setTab] = useState<Tab>("list");
  const [lookupSymbol, setLookupSymbol] = useState("");

  const filtered = trades?.filter(
    (t) => !filter || t.symbol.includes(filter.toUpperCase()),
  );

  // Calendar heatmap data — aggregate daily P&L
  const calendarData = useMemo(() => {
    if (!trades) return [];
    const byDate: Record<string, number> = {};
    for (const t of trades) {
      if (!t.trade_date) continue;
      byDate[t.trade_date] = (byDate[t.trade_date] || 0) + t.realized_pnl;
    }
    return Object.entries(byDate).map(([date, pnl]) => ({ date, pnl: Math.round(pnl * 100) / 100 }));
  }, [trades]);

  // Stop discipline: trades where stop was respected vs breached
  const stopDiscipline = useMemo(() => {
    if (!trades) return { total: 0, lossTrades: 0, avgLoss: 0 };
    const losses = trades.filter((t) => t.realized_pnl < 0);
    const avgLoss = losses.length > 0
      ? losses.reduce((s, t) => s + t.realized_pnl, 0) / losses.length
      : 0;
    return {
      total: trades.length,
      lossTrades: losses.length,
      avgLoss: Math.round(avgLoss * 100) / 100,
    };
  }, [trades]);

  // Symbol lookup
  const symbolTrades = useMemo(() => {
    if (!trades || !lookupSymbol) return [];
    return trades.filter((t) => t.symbol === lookupSymbol.toUpperCase());
  }, [trades, lookupSymbol]);

  const symbolStats = useMemo(() => {
    if (!symbolTrades.length) return null;
    const wins = symbolTrades.filter((t) => t.realized_pnl >= 0).length;
    const totalPnl = symbolTrades.reduce((s, t) => s + t.realized_pnl, 0);
    return {
      count: symbolTrades.length,
      wins,
      losses: symbolTrades.length - wins,
      winRate: ((wins / symbolTrades.length) * 100).toFixed(1),
      totalPnl: totalPnl.toFixed(2),
    };
  }, [symbolTrades]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Trade History</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border-subtle pb-1">
        {(["list", "calendar", "stop-discipline", "symbol-lookup"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-t px-3 py-1.5 text-xs font-medium ${
              tab === t ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {t === "list" ? "List" : t === "calendar" ? "Calendar" : t === "stop-discipline" ? "Stop Discipline" : "Symbol Lookup"}
          </button>
        ))}
      </div>

      {tab === "list" && (
        <>
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by symbol..."
            className="w-40 rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          />

          {isLoading && <SkeletonTable rows={8} />}

          {filtered && filtered.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-text-muted">
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Symbol</th>
                    <th className="pb-2">Type</th>
                    <th className="pb-2">Proceeds</th>
                    <th className="pb-2">Cost</th>
                    <th className="pb-2">P&L</th>
                    <th className="pb-2">Wash</th>
                    <th className="pb-2">Days</th>
                    <th className="pb-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t, i) => (
                    <tr key={i} className="border-t border-border-subtle">
                      <td className="py-2 text-text-muted">{t.trade_date}</td>
                      <td className="py-2 font-medium text-text-primary">{t.symbol}</td>
                      <td className="py-2 text-xs text-text-faint">{t.asset_type}</td>
                      <td className="py-2 font-mono text-text-secondary">${t.proceeds.toFixed(2)}</td>
                      <td className="py-2 font-mono text-text-secondary">${t.cost_basis.toFixed(2)}</td>
                      <td className={`py-2 font-mono font-medium ${t.realized_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                        ${t.realized_pnl.toFixed(2)}
                      </td>
                      <td className="py-2 text-warning-text">
                        {t.wash_sale_disallowed > 0 ? `$${t.wash_sale_disallowed.toFixed(2)}` : "—"}
                      </td>
                      <td className="py-2 text-text-faint">{t.holding_days ?? "—"}</td>
                      <td className="py-2 text-xs text-text-faint">{t.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {filtered && filtered.length === 0 && !isLoading && (
            <p className="text-sm text-text-faint">No trades found. Import your brokerage statements to see history.</p>
          )}
        </>
      )}

      {tab === "calendar" && (
        <CalendarHeatmap data={calendarData} />
      )}

      {tab === "stop-discipline" && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-border-subtle bg-surface-2 p-4">
              <p className="text-xs text-text-muted">Total Trades</p>
              <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{stopDiscipline.total}</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface-2 p-4">
              <p className="text-xs text-text-muted">Loss Trades</p>
              <p className="mt-1 font-mono text-2xl font-bold text-bearish-text">{stopDiscipline.lossTrades}</p>
            </div>
            <div className="rounded-lg border border-border-subtle bg-surface-2 p-4">
              <p className="text-xs text-text-muted">Avg Loss</p>
              <p className="mt-1 font-mono text-2xl font-bold text-bearish-text">${stopDiscipline.avgLoss}</p>
            </div>
          </div>
          <p className="text-sm text-text-muted">
            Stop discipline measures how consistently you limit losses. A lower average loss indicates good stop discipline.
          </p>
        </div>
      )}

      {tab === "symbol-lookup" && (
        <div className="space-y-4">
          <input
            type="text"
            value={lookupSymbol}
            onChange={(e) => setLookupSymbol(e.target.value.toUpperCase())}
            placeholder="Enter symbol..."
            className="w-40 rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          {symbolStats && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <div className="rounded-lg border border-border-subtle bg-surface-2 p-3">
                <p className="text-xs text-text-muted">Trades</p>
                <p className="font-mono text-lg font-bold text-text-primary">{symbolStats.count}</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-2 p-3">
                <p className="text-xs text-text-muted">Wins</p>
                <p className="font-mono text-lg font-bold text-bullish-text">{symbolStats.wins}</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-2 p-3">
                <p className="text-xs text-text-muted">Losses</p>
                <p className="font-mono text-lg font-bold text-bearish-text">{symbolStats.losses}</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-2 p-3">
                <p className="text-xs text-text-muted">Win Rate</p>
                <p className="font-mono text-lg font-bold text-text-primary">{symbolStats.winRate}%</p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-2 p-3">
                <p className="text-xs text-text-muted">Total P&L</p>
                <p className={`font-mono text-lg font-bold ${parseFloat(symbolStats.totalPnl) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                  ${symbolStats.totalPnl}
                </p>
              </div>
            </div>
          )}
          {symbolTrades.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-text-muted">
                    <th className="pb-2">Date</th>
                    <th className="pb-2">Proceeds</th>
                    <th className="pb-2">Cost</th>
                    <th className="pb-2">P&L</th>
                    <th className="pb-2">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {symbolTrades.map((t, i) => (
                    <tr key={i} className="border-t border-border-subtle">
                      <td className="py-2 text-text-muted">{t.trade_date}</td>
                      <td className="py-2 font-mono text-text-secondary">${t.proceeds.toFixed(2)}</td>
                      <td className="py-2 font-mono text-text-secondary">${t.cost_basis.toFixed(2)}</td>
                      <td className={`py-2 font-mono font-medium ${t.realized_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                        ${t.realized_pnl.toFixed(2)}
                      </td>
                      <td className="py-2 text-xs text-text-faint">{t.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
