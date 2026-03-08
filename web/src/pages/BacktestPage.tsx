import { useState } from "react";
import { useRunBacktest, type BacktestResult } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

export default function BacktestPage() {
  const { canAccessBacktest } = useFeatureGate();

  if (!canAccessBacktest) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-gray-500">Backtesting requires a Pro subscription.</p>
      </div>
    );
  }

  return <BacktestContent />;
}

function BacktestContent() {
  const [symbols, setSymbols] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [results, setResults] = useState<BacktestResult[] | null>(null);

  const runBacktest = useRunBacktest();

  function handleRun(e: React.FormEvent) {
    e.preventDefault();
    const syms = symbols
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (syms.length === 0 || !startDate || !endDate) return;

    runBacktest.mutate(
      { symbols: syms, start_date: startDate, end_date: endDate },
      { onSuccess: (data) => setResults(data) },
    );
  }

  const totalPnl = results?.reduce((s, r) => s + r.total_pnl, 0) ?? 0;
  const totalSignals = results?.reduce((s, r) => s + r.total_signals, 0) ?? 0;
  const totalWins = results?.reduce((s, r) => s + r.win_count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Backtest</h1>

      {/* Config form */}
      <div className="rounded-lg bg-gray-900 p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-400">Run Backtest</h2>
        <form onSubmit={handleRun} className="flex flex-wrap gap-2">
          <input
            type="text"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value.toUpperCase())}
            placeholder="Symbols (comma-separated)"
            required
            className="w-56 rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
            className="rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            required
            className="rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={runBacktest.isPending}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {runBacktest.isPending ? "Running..." : "Run"}
          </button>
        </form>
      </div>

      {runBacktest.isError && (
        <p className="text-sm text-red-400">
          {runBacktest.error instanceof Error ? runBacktest.error.message : "Backtest failed"}
        </p>
      )}

      {/* Summary */}
      {results && results.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Total P&L</p>
              <p
                className={`mt-1 text-2xl font-bold ${
                  totalPnl >= 0 ? "text-green-400" : "text-red-400"
                }`}
              >
                ${totalPnl.toFixed(2)}
              </p>
            </div>
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Signals</p>
              <p className="mt-1 text-2xl font-bold">{totalSignals}</p>
            </div>
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Win Rate</p>
              <p className="mt-1 text-2xl font-bold">
                {totalSignals > 0 ? ((totalWins / totalSignals) * 100).toFixed(1) : 0}%
              </p>
            </div>
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Symbols Tested</p>
              <p className="mt-1 text-2xl font-bold">{results.length}</p>
            </div>
          </div>

          {/* Per-symbol results */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Signals</th>
                  <th className="pb-2">Wins</th>
                  <th className="pb-2">Losses</th>
                  <th className="pb-2">Win Rate</th>
                  <th className="pb-2">Avg R:R</th>
                  <th className="pb-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.symbol} className="border-t border-gray-800">
                    <td className="py-2 font-medium">{r.symbol}</td>
                    <td className="py-2">{r.total_signals}</td>
                    <td className="py-2 text-green-400">{r.win_count}</td>
                    <td className="py-2 text-red-400">{r.loss_count}</td>
                    <td className="py-2">{r.win_rate}%</td>
                    <td className="py-2">{r.avg_rr.toFixed(2)}</td>
                    <td
                      className={`py-2 font-medium ${
                        r.total_pnl >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      ${r.total_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {results && results.length === 0 && (
        <p className="text-sm text-gray-500">No signals found in the selected date range.</p>
      )}
    </div>
  );
}
