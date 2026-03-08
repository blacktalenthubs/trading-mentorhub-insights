import { usePaperPositions, usePaperHistory, usePaperAccount } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

export default function PaperTradingPage() {
  const { canAccessPaperTrading } = useFeatureGate();

  if (!canAccessPaperTrading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-gray-500">Paper Trading requires a Pro subscription.</p>
      </div>
    );
  }

  return <PaperTradingContent />;
}

function PaperTradingContent() {
  const { data: positions, isLoading: loadingPositions } = usePaperPositions();
  const { data: history, isLoading: loadingHistory } = usePaperHistory();
  const { data: account } = usePaperAccount();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Paper Trading</h1>

      {/* Account summary */}
      {account && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg bg-gray-900 p-4">
            <p className="text-xs text-gray-500">Open Positions</p>
            <p className="mt-1 text-2xl font-bold">{account.open_positions}</p>
          </div>
          <div className="rounded-lg bg-gray-900 p-4">
            <p className="text-xs text-gray-500">Total Closed</p>
            <p className="mt-1 text-2xl font-bold">{account.total_closed}</p>
          </div>
          <div className="rounded-lg bg-gray-900 p-4">
            <p className="text-xs text-gray-500">Total P&L</p>
            <p
              className={`mt-1 text-2xl font-bold ${
                account.total_pnl >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              ${account.total_pnl.toFixed(2)}
            </p>
          </div>
          <div className="rounded-lg bg-gray-900 p-4">
            <p className="text-xs text-gray-500">Win Rate</p>
            <p className="mt-1 text-2xl font-bold">{account.win_rate}%</p>
          </div>
        </div>
      )}

      {/* Open positions */}
      <div>
        <h2 className="mb-2 text-sm font-medium text-gray-400">Open Positions</h2>
        {loadingPositions && <p className="text-sm text-gray-500">Loading...</p>}
        {positions && positions.length > 0 ? (
          <div className="space-y-2">
            {positions.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg bg-gray-900 px-4 py-3"
              >
                <div>
                  <span className="font-medium">{p.symbol}</span>
                  <span className="ml-2 text-sm text-gray-400">
                    {p.shares} shares @ ${p.entry_price?.toFixed(2) ?? "—"}
                  </span>
                </div>
                <span className="text-xs text-gray-500">{p.session_date}</span>
              </div>
            ))}
          </div>
        ) : (
          !loadingPositions && (
            <p className="text-sm text-gray-500">No open paper positions.</p>
          )
        )}
      </div>

      {/* Closed history */}
      <div>
        <h2 className="mb-2 text-sm font-medium text-gray-400">Closed Trades</h2>
        {loadingHistory && <p className="text-sm text-gray-500">Loading...</p>}
        {history && history.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
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
                  <tr key={t.id} className="border-t border-gray-800">
                    <td className="py-2 font-medium">{t.symbol}</td>
                    <td className="py-2 text-xs text-gray-400">{t.direction}</td>
                    <td className="py-2">{t.shares}</td>
                    <td className="py-2">${t.entry_price?.toFixed(2) ?? "—"}</td>
                    <td className="py-2">${t.exit_price?.toFixed(2) ?? "—"}</td>
                    <td
                      className={`py-2 font-medium ${
                        (t.pnl ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      ${t.pnl?.toFixed(2) ?? "—"}
                    </td>
                    <td className="py-2 text-gray-500">{t.session_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          !loadingHistory && (
            <p className="text-sm text-gray-500">No closed paper trades yet.</p>
          )
        )}
      </div>
    </div>
  );
}
