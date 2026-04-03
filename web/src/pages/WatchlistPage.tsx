/** Dedicated watchlist management page — table layout with add/remove. */

import { useState } from "react";
import { useWatchlist, useAddSymbol, useRemoveSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import Card from "../components/ui/Card";
import { Plus, Loader2, Trash2, Star } from "lucide-react";

export default function WatchlistPage() {
  const { data: watchlist, isLoading } = useWatchlist();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const { maxWatchlistSize, isPro } = useFeatureGate();
  const [input, setInput] = useState("");

  const count = watchlist?.length ?? 0;
  const atLimit = count >= maxWatchlistSize;

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    addSymbol.mutate(sym, { onSuccess: () => setInput("") });
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star className="h-5 w-5 text-accent" />
          <h1 className="font-display text-2xl font-bold">Watchlist</h1>
          <span className="rounded-full bg-surface-4 px-2.5 py-1 text-xs font-medium text-text-muted">
            {count}{maxWatchlistSize < Infinity ? ` / ${maxWatchlistSize}` : ""}
          </span>
        </div>
      </div>

      {/* Add form */}
      <Card padding="md">
        <form onSubmit={handleAdd} className="flex items-center gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Enter ticker symbol (e.g. AAPL, NVDA, BTC-USD)"
            disabled={!!atLimit}
            className="flex-1 rounded-lg border border-border-subtle bg-surface-3 px-4 py-2.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none disabled:opacity-40"
          />
          <button
            type="submit"
            disabled={!!atLimit || !input.trim() || addSymbol.isPending}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40 active:scale-95"
          >
            {addSymbol.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Add Symbol
          </button>
        </form>

        {addSymbol.error && (
          <p className="mt-2 text-xs text-bearish-text">
            {addSymbol.error instanceof Error ? addSymbol.error.message : "Failed to add symbol"}
          </p>
        )}
        {atLimit && !isPro && (
          <p className="mt-2 text-xs text-warning-text">
            Free tier limit reached. Upgrade to Pro for unlimited symbols.
          </p>
        )}
      </Card>

      {/* Watchlist table */}
      {isLoading && (
        <div className="flex items-center gap-2 py-8">
          <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          <span className="text-sm text-text-muted">Loading watchlist...</span>
        </div>
      )}

      {watchlist && watchlist.length > 0 && (
        <Card padding="none">
          <div className="divide-y divide-border-subtle">
            {watchlist.map((item, i) => (
              <div
                key={item.id}
                className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-surface-3/50"
              >
                <div className="flex items-center gap-4">
                  <span className="w-6 text-center text-xs text-text-faint">{i + 1}</span>
                  <span className="text-sm font-semibold text-text-primary">{item.symbol}</span>
                </div>
                <button
                  onClick={() => removeSymbol.mutate(item.symbol)}
                  disabled={removeSymbol.isPending}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-text-muted transition-colors hover:bg-bearish-muted hover:text-bearish-text active:scale-95"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {watchlist && watchlist.length === 0 && !isLoading && (
        <div className="flex flex-col items-center gap-2 py-12 text-center">
          <Star className="h-10 w-10 text-text-faint" />
          <p className="text-text-muted">Your watchlist is empty</p>
          <p className="text-sm text-text-faint">Add ticker symbols above to start tracking stocks and crypto.</p>
        </div>
      )}
    </div>
  );
}
