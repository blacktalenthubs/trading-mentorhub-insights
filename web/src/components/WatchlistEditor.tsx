import { useState } from "react";
import { useWatchlist, useAddSymbol, useRemoveSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

export default function WatchlistEditor() {
  const { data: watchlist, isLoading } = useWatchlist();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const { maxWatchlistSize } = useFeatureGate();
  const [input, setInput] = useState("");

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    addSymbol.mutate(sym, { onSuccess: () => setInput("") });
  }

  if (isLoading) return <p className="text-sm text-gray-500">Loading...</p>;

  const atLimit = watchlist && watchlist.length >= maxWatchlistSize;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-gray-400">
          Watchlist ({watchlist?.length ?? 0}
          {maxWatchlistSize < Infinity ? `/${maxWatchlistSize}` : ""})
        </h2>
      </div>

      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          placeholder="Add symbol..."
          disabled={!!atLimit}
          className="flex-1 rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!!atLimit || !input.trim()}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          Add
        </button>
      </form>
      {atLimit && (
        <p className="text-xs text-yellow-500">
          Free tier limit reached. Upgrade to Pro for unlimited symbols.
        </p>
      )}

      {addSymbol.error && (
        <p className="text-xs text-red-400">
          {addSymbol.error instanceof Error ? addSymbol.error.message : "Failed to add"}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {watchlist?.map((item) => (
          <div
            key={item.id}
            className="group flex items-center gap-1 rounded bg-gray-800 px-2.5 py-1 text-sm"
          >
            <span>{item.symbol}</span>
            <button
              onClick={() => removeSymbol.mutate(item.symbol)}
              className="ml-1 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
            >
              x
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
