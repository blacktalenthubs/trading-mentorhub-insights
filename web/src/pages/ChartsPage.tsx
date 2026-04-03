import { useState } from "react";
import { useOHLCV, useChartLevels, useAddChartLevel, useDeleteChartLevel, useWatchlist, usePriorDay } from "../api/hooks";
import CandlestickChart from "../components/CandlestickChart";
import WatchlistBar from "../components/WatchlistBar";

const PERIODS = ["1mo", "3mo", "6mo", "1y"];
const MA_OPTIONS = [
  { key: "sma20", label: "SMA 20", color: "#3b82f6" },
  { key: "sma50", label: "SMA 50", color: "#f59e0b" },
  { key: "ema9", label: "EMA 9", color: "#a78bfa" },
  { key: "vwap", label: "VWAP", color: "#06b6d4" },
] as const;

type MAKey = (typeof MA_OPTIONS)[number]["key"];

export default function ChartsPage() {
  const { data: watchlist } = useWatchlist();
  const [symbol, setSymbol] = useState("");
  const [period, setPeriod] = useState("3mo");
  const [newPrice, setNewPrice] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [enabledMAs, setEnabledMAs] = useState<Set<MAKey>>(new Set(["sma20", "sma50"]));

  const activeSymbol = symbol || watchlist?.[0]?.symbol || "";
  const { data: bars } = useOHLCV(activeSymbol, period);
  const { data: levels } = useChartLevels(activeSymbol);
  const { data: priorDay } = usePriorDay(activeSymbol);
  const addLevel = useAddChartLevel();
  const deleteLevel = useDeleteChartLevel();

  function toggleMA(key: MAKey) {
    setEnabledMAs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function handleAddLevel(e: React.FormEvent) {
    e.preventDefault();
    const price = parseFloat(newPrice);
    if (!price || !activeSymbol) return;
    addLevel.mutate(
      { symbol: activeSymbol, price, label: newLabel },
      { onSuccess: () => { setNewPrice(""); setNewLabel(""); } },
    );
  }

  // Build indicator config for chart
  const indicators = MA_OPTIONS
    .filter((m) => enabledMAs.has(m.key))
    .map((m) => ({ key: m.key, color: m.color }));

  // Prior day high/low as extra levels (API returns "high"/"low" for the prior completed day)
  const priorLevels = [];
  if (priorDay) {
    const pd = priorDay as Record<string, number>;
    if (pd.high) priorLevels.push({ id: -1, symbol: activeSymbol, price: pd.high, label: "Prior High", color: "#22c55e" });
    if (pd.low) priorLevels.push({ id: -2, symbol: activeSymbol, price: pd.low, label: "Prior Low", color: "#ef4444" });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Charts</h1>
        <div className="flex items-center gap-2">
          {PERIODS.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                period === p
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted hover:bg-surface-4"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Watchlist symbol selector */}
      <WatchlistBar
        selected={activeSymbol}
        onSelect={(sym) => setSymbol(sym)}
        editable={true}
        compact={false}
      />

      {/* MA/VWAP toggles */}
      <div className="flex flex-wrap gap-2">
        {MA_OPTIONS.map((m) => (
          <button
            key={m.key}
            onClick={() => toggleMA(m.key)}
            className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
              enabledMAs.has(m.key)
                ? "text-white"
                : "bg-surface-3 text-text-muted hover:bg-surface-4"
            }`}
            style={enabledMAs.has(m.key) ? { backgroundColor: m.color } : undefined}
          >
            {m.label}
          </button>
        ))}
      </div>

      {bars && bars.length > 0 ? (
        <CandlestickChart
          data={bars}
          levels={[...(levels || []), ...priorLevels]}
          height={500}
          indicators={indicators}
        />
      ) : (
        <div className="flex h-[500px] items-center justify-center rounded-lg bg-surface-2">
          <p className="text-text-faint">Select a symbol to view chart</p>
        </div>
      )}

      {/* Custom Levels */}
      <div className="rounded-lg border border-border-subtle bg-surface-2 p-4">
        <h2 className="mb-3 text-sm font-medium text-text-muted">Custom Levels</h2>
        <form onSubmit={handleAddLevel} className="flex gap-2">
          <input
            type="number"
            step="0.01"
            value={newPrice}
            onChange={(e) => setNewPrice(e.target.value)}
            placeholder="Price"
            className="w-28 rounded border border-border-subtle bg-surface-3 px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="Label"
            className="w-32 rounded border border-border-subtle bg-surface-3 px-2 py-1 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            className="rounded bg-accent px-3 py-1 text-sm font-medium text-white hover:bg-accent-hover"
          >
            Add
          </button>
        </form>
        {levels && levels.length > 0 && (
          <div className="mt-3 space-y-1">
            {levels.map((lvl) => (
              <div key={lvl.id} className="flex items-center justify-between text-sm">
                <span className="text-text-secondary">
                  <span className="mr-2 inline-block h-3 w-3 rounded" style={{ backgroundColor: lvl.color }} />
                  ${lvl.price.toFixed(2)} {lvl.label && `— ${lvl.label}`}
                </span>
                <button
                  onClick={() => deleteLevel.mutate({ id: lvl.id, symbol: activeSymbol })}
                  className="text-text-faint hover:text-bearish-text"
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
