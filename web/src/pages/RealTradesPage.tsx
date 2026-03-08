import { useState } from "react";
import {
  useOpenTrades,
  useClosedTrades,
  useRealTradeStats,
  useOpenRealTrade,
  useCloseRealTrade,
} from "../api/hooks";

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg bg-gray-900 p-3">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold ${color || "text-white"}`}>{value}</p>
    </div>
  );
}

export default function RealTradesPage() {
  const { data: openTrades } = useOpenTrades();
  const { data: closedTrades } = useClosedTrades();
  const { data: stats } = useRealTradeStats();
  const openTrade = useOpenRealTrade();
  const closeTrade = useCloseRealTrade();

  const [symbol, setSymbol] = useState("");
  const [entryPrice, setEntryPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [targetPrice, setTargetPrice] = useState("");

  // Close modal state
  const [closingId, setClosingId] = useState<number | null>(null);
  const [exitPrice, setExitPrice] = useState("");

  function handleOpen(e: React.FormEvent) {
    e.preventDefault();
    openTrade.mutate(
      {
        symbol: symbol.toUpperCase(),
        entry_price: parseFloat(entryPrice),
        stop_price: stopPrice ? parseFloat(stopPrice) : undefined,
        target_price: targetPrice ? parseFloat(targetPrice) : undefined,
      },
      { onSuccess: () => { setSymbol(""); setEntryPrice(""); setStopPrice(""); setTargetPrice(""); } },
    );
  }

  function handleClose() {
    if (closingId === null || !exitPrice) return;
    closeTrade.mutate(
      { id: closingId, exit_price: parseFloat(exitPrice) },
      { onSuccess: () => { setClosingId(null); setExitPrice(""); } },
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Trades</h1>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox
            label="Total P&L"
            value={`$${stats.total_pnl.toFixed(2)}`}
            color={stats.total_pnl >= 0 ? "text-green-400" : "text-red-400"}
          />
          <StatBox label="Win Rate" value={`${stats.win_rate}%`} />
          <StatBox label="Trades" value={`${stats.total_trades}`} />
          <StatBox
            label="Expectancy"
            value={`$${stats.expectancy.toFixed(2)}`}
            color={stats.expectancy >= 0 ? "text-green-400" : "text-red-400"}
          />
        </div>
      )}

      {/* Open Trade Form */}
      <div className="rounded-lg bg-gray-900 p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-400">Open New Trade</h2>
        <form onSubmit={handleOpen} className="flex flex-wrap gap-2">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol"
            required
            className="w-24 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="number"
            step="0.01"
            value={entryPrice}
            onChange={(e) => setEntryPrice(e.target.value)}
            placeholder="Entry $"
            required
            className="w-28 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="number"
            step="0.01"
            value={stopPrice}
            onChange={(e) => setStopPrice(e.target.value)}
            placeholder="Stop $"
            className="w-28 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="number"
            step="0.01"
            value={targetPrice}
            onChange={(e) => setTargetPrice(e.target.value)}
            placeholder="Target $"
            className="w-28 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={openTrade.isPending}
            className="rounded bg-green-600 px-4 py-1.5 text-sm font-medium hover:bg-green-700 disabled:opacity-50"
          >
            Open
          </button>
        </form>
      </div>

      {/* Open Positions */}
      {openTrades && openTrades.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-400">Open Positions</h2>
          <div className="space-y-2">
            {openTrades.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-lg bg-gray-900 px-4 py-3"
              >
                <div>
                  <span className="font-medium">{t.symbol}</span>
                  <span className="ml-2 text-sm text-gray-400">
                    {t.shares} shares @ ${t.entry_price.toFixed(2)}
                  </span>
                </div>
                <button
                  onClick={() => setClosingId(t.id)}
                  className="rounded bg-red-600 px-3 py-1 text-xs font-medium hover:bg-red-700"
                >
                  Close
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Close modal */}
      {closingId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="rounded-lg bg-gray-900 p-6 w-[calc(100%-2rem)] max-w-80 space-y-4">
            <h3 className="font-bold">Close Trade</h3>
            <input
              type="number"
              step="0.01"
              value={exitPrice}
              onChange={(e) => setExitPrice(e.target.value)}
              placeholder="Exit Price $"
              className="w-full rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={handleClose}
                className="flex-1 rounded bg-red-600 py-2 text-sm font-medium hover:bg-red-700"
              >
                Confirm Close
              </button>
              <button
                onClick={() => setClosingId(null)}
                className="flex-1 rounded bg-gray-800 py-2 text-sm hover:bg-gray-700"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Closed Trades */}
      {closedTrades && closedTrades.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-400">Recent Closed</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Entry</th>
                  <th className="pb-2">Exit</th>
                  <th className="pb-2">Shares</th>
                  <th className="pb-2">P&L</th>
                  <th className="pb-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {closedTrades.map((t) => (
                  <tr key={t.id} className="border-t border-gray-800">
                    <td className="py-2 font-medium">{t.symbol}</td>
                    <td className="py-2">${t.entry_price.toFixed(2)}</td>
                    <td className="py-2">${t.exit_price?.toFixed(2)}</td>
                    <td className="py-2">{t.shares}</td>
                    <td
                      className={`py-2 font-medium ${
                        (t.pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      ${t.pnl?.toFixed(2)}
                    </td>
                    <td className="py-2 text-gray-500">{t.session_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
