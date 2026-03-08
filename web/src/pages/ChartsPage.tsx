import { useState } from "react";
import { useOHLCV, useChartLevels, useAddChartLevel, useDeleteChartLevel, useWatchlist } from "../api/hooks";
import CandlestickChart from "../components/CandlestickChart";

export default function ChartsPage() {
  const { data: watchlist } = useWatchlist();
  const [symbol, setSymbol] = useState("");
  const [period, setPeriod] = useState("3mo");
  const [newPrice, setNewPrice] = useState("");
  const [newLabel, setNewLabel] = useState("");

  const activeSymbol = symbol || watchlist?.[0]?.symbol || "";
  const { data: bars } = useOHLCV(activeSymbol, period);
  const { data: levels } = useChartLevels(activeSymbol);
  const addLevel = useAddChartLevel();
  const deleteLevel = useDeleteChartLevel();

  function handleAddLevel(e: React.FormEvent) {
    e.preventDefault();
    const price = parseFloat(newPrice);
    if (!price || !activeSymbol) return;
    addLevel.mutate(
      { symbol: activeSymbol, price, label: newLabel },
      { onSuccess: () => { setNewPrice(""); setNewLabel(""); } },
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold">Charts</h1>
        <select
          value={activeSymbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm"
        >
          {watchlist?.map((w) => (
            <option key={w.id} value={w.symbol}>
              {w.symbol}
            </option>
          ))}
        </select>
        {["1mo", "3mo", "6mo", "1y"].map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`rounded px-2 py-1 text-xs ${
              period === p ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"
            }`}
          >
            {p}
          </button>
        ))}
      </div>

      {bars && bars.length > 0 ? (
        <CandlestickChart data={bars} levels={levels || []} height={500} />
      ) : (
        <div className="flex h-[500px] items-center justify-center rounded-lg bg-gray-900">
          <p className="text-gray-500">Select a symbol to view chart</p>
        </div>
      )}

      {/* Custom Levels */}
      <div className="rounded-lg bg-gray-900 p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-400">Custom Levels</h2>
        <form onSubmit={handleAddLevel} className="flex gap-2">
          <input
            type="number"
            step="0.01"
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            placeholder="Price"
            className="w-28 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
          />
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label"
            className="w-32 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button
            type="submit"
            className="rounded bg-blue-600 px-3 py-1 text-sm hover:bg-blue-700"
          >
            Add
          </button>
        </form>
        {levels && levels.length > 0 && (
          <div className="mt-3 space-y-1">
            {levels.map((lvl) => (
              <div key={lvl.id} className="flex items-center justify-between text-sm">
                <span>
                  <span className="inline-block w-3 h-3 rounded mr-2" style={{ backgroundColor: lvl.color }} />
                  ${lvl.price.toFixed(2)} {lvl.label && `— ${lvl.label}`}
                </span>
                <button
                  onClick={() => deleteLevel.mutate({ id: lvl.id, symbol: activeSymbol })}
                  className="text-gray-600 hover:text-red-400"
                >
                  x
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
