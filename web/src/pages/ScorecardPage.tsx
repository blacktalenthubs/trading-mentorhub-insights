import { useMonthlyStats, useRealTradeStats } from "../api/hooks";
import { SkeletonGrid } from "../components/LoadingSkeleton";

export default function ScorecardPage() {
  const { data: monthly, isLoading: loadingMonthly } = useMonthlyStats();
  const { data: stats } = useRealTradeStats();

  const totalPnl = monthly?.reduce((sum, m) => sum + m.total_pnl, 0) ?? 0;
  const totalTrades = monthly?.reduce((sum, m) => sum + m.total_trades, 0) ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Scorecard</h1>

      {/* Summary stats */}
      {loadingMonthly && <SkeletonGrid count={4} />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-gray-900 p-4">
          <p className="text-xs text-gray-500">Total P&L (Imported)</p>
          <p className={`mt-1 text-2xl font-bold ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            ${totalPnl.toFixed(2)}
          </p>
        </div>
        <div className="rounded-lg bg-gray-900 p-4">
          <p className="text-xs text-gray-500">Total Trades</p>
          <p className="mt-1 text-2xl font-bold">{totalTrades}</p>
        </div>
        {stats && (
          <>
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Live Win Rate</p>
              <p className="mt-1 text-2xl font-bold">{stats.win_rate}%</p>
            </div>
            <div className="rounded-lg bg-gray-900 p-4">
              <p className="text-xs text-gray-500">Live P&L</p>
              <p className={`mt-1 text-2xl font-bold ${stats.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                ${stats.total_pnl.toFixed(2)}
              </p>
            </div>
          </>
        )}
      </div>

      {/* Monthly breakdown */}
      {monthly && monthly.length > 0 && (
        <div>
          <h2 className="mb-3 text-sm font-medium text-gray-400">Monthly Breakdown</h2>

          {/* Bar chart */}
          <div className="flex items-end gap-1 h-40 mb-4">
            {monthly.slice(0, 12).reverse().map((m) => {
              const maxPnl = Math.max(...monthly.map((x) => Math.abs(x.total_pnl)), 1);
              const pct = Math.abs(m.total_pnl) / maxPnl * 100;
              return (
                <div key={m.month} className="flex flex-1 flex-col items-center">
                  <div
                    className={`w-full rounded-t ${m.total_pnl >= 0 ? "bg-green-600" : "bg-red-600"}`}
                    style={{ height: `${Math.max(pct, 2)}%` }}
                  />
                  <p className="mt-1 text-[10px] text-gray-500">{m.month.slice(5)}</p>
                </div>
              );
            })}
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
                  <th className="pb-2">Month</th>
                  <th className="pb-2">Trades</th>
                  <th className="pb-2">Wins</th>
                  <th className="pb-2">Losses</th>
                  <th className="pb-2">Win Rate</th>
                  <th className="pb-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {monthly.map((m) => (
                  <tr key={m.month} className="border-t border-gray-800">
                    <td className="py-2 font-medium">{m.month}</td>
                    <td className="py-2">{m.total_trades}</td>
                    <td className="py-2 text-green-400">{m.win_count}</td>
                    <td className="py-2 text-red-400">{m.loss_count}</td>
                    <td className="py-2">{m.win_rate}%</td>
                    <td className={`py-2 font-medium ${m.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      ${m.total_pnl.toFixed(2)}
                    </td>
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
