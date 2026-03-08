import { useState } from "react";
import { useTradeHistory } from "../api/hooks";
import { SkeletonTable } from "../components/LoadingSkeleton";

export default function HistoryPage() {
  const { data: trades, isLoading } = useTradeHistory();
  const [filter, setFilter] = useState("");

  const filtered = trades?.filter(
    (t) => !filter || t.symbol.includes(filter.toUpperCase()),
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trade History</h1>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by symbol..."
          className="w-40 rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      {isLoading && <SkeletonTable rows={8} />}

      {filtered && filtered.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500">
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
                <tr key={i} className="border-t border-gray-800">
                  <td className="py-2 text-gray-400">{t.trade_date}</td>
                  <td className="py-2 font-medium">{t.symbol}</td>
                  <td className="py-2 text-xs text-gray-500">{t.asset_type}</td>
                  <td className="py-2">${t.proceeds.toFixed(2)}</td>
                  <td className="py-2">${t.cost_basis.toFixed(2)}</td>
                  <td
                    className={`py-2 font-medium ${
                      t.realized_pnl >= 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    ${t.realized_pnl.toFixed(2)}
                  </td>
                  <td className="py-2 text-yellow-500">
                    {t.wash_sale_disallowed > 0 ? `$${t.wash_sale_disallowed.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2 text-gray-500">{t.holding_days ?? "—"}</td>
                  <td className="py-2 text-xs text-gray-600">{t.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {filtered && filtered.length === 0 && !isLoading && (
        <p className="text-sm text-gray-500">No trades found. Import your brokerage statements to see history.</p>
      )}
    </div>
  );
}
