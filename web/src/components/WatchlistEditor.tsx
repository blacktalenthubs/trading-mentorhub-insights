/** Full watchlist management panel — add, remove, count, tier limit.
 *  Uses design system tokens. Renders as a Card with inline editing.
 */

import { useState } from "react";
import { X, Plus, Loader2, Star } from "lucide-react";
import { useWatchlist, useAddSymbol, useRemoveSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import Card from "./ui/Card";

interface Props {
  /** Optional className */
  className?: string;
}

export default function WatchlistEditor({ className = "" }: Props) {
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
    <Card padding="md" className={className}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star className="h-4 w-4 text-accent" />
          <h2 className="font-display text-sm font-semibold text-text-primary">
            Watchlist
          </h2>
          <span className="rounded-full bg-surface-4 px-2 py-0.5 text-xs font-medium text-text-muted">
            {count}{maxWatchlistSize < Infinity ? `/${maxWatchlistSize}` : ""}
          </span>
        </div>

        {/* Inline add form */}
        <form onSubmit={handleAdd} className="flex items-center gap-1.5">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value.toUpperCase())}
            placeholder="Add symbol..."
            disabled={!!atLimit}
            className="w-28 rounded-md border border-border-subtle bg-surface-3 px-2.5 py-1 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none disabled:opacity-40"
          />
          <button
            type="submit"
            disabled={!!atLimit || !input.trim() || addSymbol.isPending}
            className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40"
          >
            {addSymbol.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Plus className="h-3 w-3" />
            )}
            Add
          </button>
        </form>
      </div>

      {/* Error message */}
      {addSymbol.error && (
        <p className="mt-2 text-xs text-bearish-text">
          {addSymbol.error instanceof Error ? addSymbol.error.message : "Failed to add symbol"}
        </p>
      )}

      {/* Tier limit warning */}
      {atLimit && !isPro && (
        <p className="mt-2 text-xs text-warning-text">
          Free tier limit reached. Upgrade to Pro for unlimited symbols.
        </p>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="mt-3 flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-text-muted" />
          <span className="text-sm text-text-muted">Loading...</span>
        </div>
      )}

      {/* Symbol pills */}
      {watchlist && watchlist.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {watchlist.map((item) => (
            <div
              key={item.id}
              className="group flex items-center gap-1.5 rounded-md bg-surface-3 px-3 py-1.5 text-sm font-medium text-text-primary transition-colors hover:bg-surface-4"
            >
              <span>{item.symbol}</span>
              <button
                onClick={() => removeSymbol.mutate(item.symbol)}
                disabled={removeSymbol.isPending}
                className="flex items-center justify-center rounded-full text-text-faint opacity-0 transition-all hover:text-bearish-text group-hover:opacity-100"
                aria-label={`Remove ${item.symbol}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {watchlist && watchlist.length === 0 && !isLoading && (
        <p className="mt-3 text-sm text-text-faint">
          No symbols in your watchlist. Add tickers above to start scanning.
        </p>
      )}
    </Card>
  );
}
