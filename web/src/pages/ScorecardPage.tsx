import { useMonthlyStats, useRealTradeStats, useRealTradeEquityCurve, useImportedEquityCurve } from "../api/hooks";
import { SkeletonGrid } from "../components/LoadingSkeleton";
import EquityCurve from "../components/EquityCurve";
import Card from "../components/ui/Card";

export default function ScorecardPage() {
  const { data: monthly, isLoading: loadingMonthly } = useMonthlyStats();
  const { data: stats } = useRealTradeStats();
  const { data: liveEquity } = useRealTradeEquityCurve();
  const { data: importedEquity } = useImportedEquityCurve();

  const totalPnl = monthly?.reduce((sum, m) => sum + m.total_pnl, 0) ?? 0;
  const totalTrades = monthly?.reduce((sum, m) => sum + m.total_trades, 0) ?? 0;

  // Drawdown calculation
  let maxDrawdown = 0;
  if (liveEquity && liveEquity.length > 0) {
    let peak = 0;
    for (const p of liveEquity) {
      if (p.pnl > peak) peak = p.pnl;
      const dd = peak - p.pnl;
      if (dd > maxDrawdown) maxDrawdown = dd;
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-bold">Scorecard</h1>

      {/* Summary stats */}
      {loadingMonthly && <SkeletonGrid count={4} />}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        <Card padding="md">
          <p className="text-xs text-text-muted">Total P&L (Imported)</p>
          <p className={`mt-1 font-mono text-2xl font-bold ${totalPnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
            ${totalPnl.toFixed(2)}
          </p>
        </Card>
        <Card padding="md">
          <p className="text-xs text-text-muted">Total Trades</p>
          <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{totalTrades}</p>
        </Card>
        {stats && (
          <>
            <Card padding="md">
              <p className="text-xs text-text-muted">Live Win Rate</p>
              <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{stats.win_rate}%</p>
            </Card>
            <Card padding="md">
              <p className="text-xs text-text-muted">Live P&L</p>
              <p className={`mt-1 font-mono text-2xl font-bold ${stats.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                ${stats.total_pnl.toFixed(2)}
              </p>
            </Card>
          </>
        )}
        <Card padding="md">
          <p className="text-xs text-text-muted">Max Drawdown</p>
          <p className="mt-1 font-mono text-2xl font-bold text-bearish-text">
            ${maxDrawdown.toFixed(2)}
          </p>
        </Card>
      </div>

      {/* Equity Curves */}
      <div className="grid gap-4 md:grid-cols-2">
        {liveEquity && liveEquity.length > 1 && (
          <Card title="Live Equity Curve" padding="sm">
            <EquityCurve data={liveEquity} height={180} lineColor="#22c55e" />
          </Card>
        )}
        {importedEquity && importedEquity.length > 1 && (
          <Card title="Imported Equity Curve" padding="sm">
            <EquityCurve data={importedEquity} height={180} lineColor="#3b82f6" />
          </Card>
        )}
      </div>

      {/* Monthly breakdown */}
      {monthly && monthly.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-sm font-semibold text-text-secondary">Monthly Breakdown</h2>

          {/* Bar chart */}
          <div className="mb-4 flex h-40 items-end gap-1">
            {monthly.slice(0, 12).reverse().map((m) => {
              const maxPnl = Math.max(...monthly.map((x) => Math.abs(x.total_pnl)), 1);
              const pct = Math.abs(m.total_pnl) / maxPnl * 100;
              return (
                <div key={m.month} className="flex flex-1 flex-col items-center">
                  <div
                    className={`w-full rounded-t ${m.total_pnl >= 0 ? "bg-bullish" : "bg-bearish"}`}
                    style={{ height: `${Math.max(pct, 2)}%` }}
                  />
                  <p className="mt-1 text-[10px] text-text-faint">{m.month.slice(5)}</p>
                </div>
              );
            })}
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
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
                  <tr key={m.month} className="border-t border-border-subtle">
                    <td className="py-2 font-medium text-text-primary">{m.month}</td>
                    <td className="py-2 text-text-secondary">{m.total_trades}</td>
                    <td className="py-2 text-bullish-text">{m.win_count}</td>
                    <td className="py-2 text-bearish-text">{m.loss_count}</td>
                    <td className="py-2 text-text-secondary">{m.win_rate}%</td>
                    <td className={`py-2 font-mono font-medium ${m.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
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
