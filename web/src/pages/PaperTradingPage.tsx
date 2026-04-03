import { usePaperPositions, usePaperHistory, usePaperAccount, usePaperEquityCurve } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import EquityCurve from "../components/EquityCurve";
import Card from "../components/ui/Card";

export default function PaperTradingPage() {
  const { canAccessPaperTrading } = useFeatureGate();

  if (!canAccessPaperTrading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-text-muted">Paper Trading requires a Pro subscription.</p>
      </div>
    );
  }

  return <PaperTradingContent />;
}

function PaperTradingContent() {
  const { data: positions, isLoading: loadingPositions } = usePaperPositions();
  const { data: history, isLoading: loadingHistory } = usePaperHistory();
  const { data: account } = usePaperAccount();
  const { data: equityCurve } = usePaperEquityCurve();

  return (
    <div className="space-y-6">
      <h1 className="font-display text-2xl font-bold">Paper Trading</h1>

      {/* Account summary */}
      {account && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Card padding="md">
            <p className="text-xs text-text-muted">Open Positions</p>
            <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{account.open_positions}</p>
          </Card>
          <Card padding="md">
            <p className="text-xs text-text-muted">Total Closed</p>
            <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{account.total_closed}</p>
          </Card>
          <Card padding="md">
            <p className="text-xs text-text-muted">Total P&L</p>
            <p className={`mt-1 font-mono text-2xl font-bold ${account.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
              ${account.total_pnl.toFixed(2)}
            </p>
          </Card>
          <Card padding="md">
            <p className="text-xs text-text-muted">Win Rate</p>
            <p className="mt-1 font-mono text-2xl font-bold text-text-primary">{account.win_rate}%</p>
          </Card>
        </div>
      )}

      {/* Equity Curve */}
      {equityCurve && equityCurve.length > 1 && (
        <Card title="Paper Equity Curve" padding="sm">
          <EquityCurve data={equityCurve} height={180} lineColor="#a78bfa" />
        </Card>
      )}

      {/* Open positions */}
      <div>
        <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Open Positions</h2>
        {loadingPositions && <p className="text-sm text-text-faint">Loading...</p>}
        {positions && positions.length > 0 ? (
          <div className="space-y-2">
            {positions.map((p) => (
              <div key={p.id} className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
                <div>
                  <span className="font-medium text-text-primary">{p.symbol}</span>
                  <span className="ml-2 text-sm text-text-muted">
                    {p.shares} shares @ ${p.entry_price?.toFixed(2) ?? "—"}
                  </span>
                </div>
                <span className="text-xs text-text-faint">{p.session_date}</span>
              </div>
            ))}
          </div>
        ) : (
          !loadingPositions && <p className="text-sm text-text-faint">No open paper positions.</p>
        )}
      </div>

      {/* Closed history */}
      <div>
        <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Closed Trades</h2>
        {loadingHistory && <p className="text-sm text-text-faint">Loading...</p>}
        {history && history.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Direction</th>
                  <th className="pb-2">Shares</th>
                  <th className="pb-2">Entry</th>
                  <th className="pb-2">Exit</th>
                  <th className="pb-2">P&L</th>
                  <th className="pb-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id} className="border-t border-border-subtle">
                    <td className="py-2 font-medium text-text-primary">{t.symbol}</td>
                    <td className="py-2 text-xs text-text-muted">{t.direction}</td>
                    <td className="py-2 text-text-secondary">{t.shares}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.entry_price?.toFixed(2) ?? "—"}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.exit_price?.toFixed(2) ?? "—"}</td>
                    <td className={`py-2 font-mono font-medium ${(t.pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      ${t.pnl?.toFixed(2) ?? "—"}
                    </td>
                    <td className="py-2 text-text-faint">{t.session_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !loadingHistory && <p className="text-sm text-text-faint">No closed paper trades yet.</p>
        )}
      </div>
    </div>
  );
}
