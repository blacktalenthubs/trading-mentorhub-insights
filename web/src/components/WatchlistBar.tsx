/** Compact watchlist symbol bar — reusable across pages.
 *  Shows symbols as clickable pills. Optionally shows add/remove controls.
 *  Use `onSelect` to handle symbol selection, `selected` to highlight active.
 */

import { useState } from "react";
import { X, Plus, Loader2 } from "lucide-react";
import { useWatchlist, useAddSymbol, useRemoveSymbol } from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";

interface Props {
  /** Currently selected symbol */
  selected?: string;
  /** Callback when a symbol is clicked */
  onSelect?: (symbol: string) => void;
  /** Show add/remove controls (default: true) */
  editable?: boolean;
  /** Compact mode — smaller pills, no add form (default: false) */
  compact?: boolean;
  /** Additional className for the container */
  className?: string;
}

export default function WatchlistBar({
  selected,
  onSelect,
  editable = true,
  compact = false,
  className = "",
}: Props) {
  const { data: watchlist, isLoading } = useWatchlist();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const { maxWatchlistSize } = useFeatureGate();
  const [input, setInput] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  const atLimit = watchlist && watchlist.length >= maxWatchlistSize;

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    addSymbol.mutate(sym, {
      onSuccess: () => {
        setInput("");
        setShowAdd(false);
      },
    });
  }

  function handleRemove(e: React.MouseEvent, symbol: string) {
    e.stopPropagation();
    removeSymbol.mutate(symbol);
  }

  if (isLoading) {
    return (
      <div className={`flex items-center gap-2 ${className}`}>
        <Loader2 className="h-4 w-4 animate-spin text-text-muted" />
        <span className="text-sm text-text-muted">Loading watchlist...</span>
      </div>
    );
  }

  const pillSize = compact ? "px-2 py-0.5 text-xs" : "px-3 py-1.5 text-sm";

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className}`}>
      {watchlist?.map((item) => {
        const isActive = selected === item.symbol;
        return (
          <button
            key={item.id}
            onClick={() => onSelect?.(item.symbol)}
            className={`group relative flex items-center gap-1 rounded-md font-medium transition-all ${pillSize} ${
              isActive
                ? "bg-accent text-white shadow-sm"
                : "bg-surface-3 text-text-secondary hover:bg-surface-4 hover:text-text-primary"
            }`}
          >
            {item.symbol}
            {editable && !compact && (
              <span
                onClick={(e) => handleRemove(e, item.symbol)}
                className={`ml-0.5 inline-flex items-center justify-center rounded-full opacity-0 transition-opacity group-hover:opacity-100 ${
                  isActive
                    ? "text-white/60 hover:text-white"
                    : "text-text-faint hover:text-bearish-text"
                }`}
              >
                <X className="h-3 w-3" />
              </span>
            )}
          </button>
        );
      })}

      {/* Add symbol button / form */}
      {editable && !atLimit && (
        <>
          {showAdd ? (
            <form onSubmit={handleAdd} className="flex items-center gap-1">
              <input
                autoFocus
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value.toUpperCase())}
                onBlur={() => {
                  if (!input.trim()) setShowAdd(false);
                }}
                placeholder="AAPL"
                className={`w-20 rounded-md border border-border-subtle bg-surface-3 text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none ${pillSize}`}
              />
              <button
                type="submit"
                disabled={!input.trim() || addSymbol.isPending}
                className={`rounded-md bg-accent font-medium text-white hover:bg-accent-hover disabled:opacity-50 ${pillSize}`}
              >
                {addSymbol.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  "Add"
                )}
              </button>
            </form>
          ) : (
            <button
              onClick={() => setShowAdd(true)}
              className={`flex items-center gap-1 rounded-md border border-dashed border-border-subtle text-text-muted transition-colors hover:border-accent hover:text-accent ${pillSize}`}
            >
              <Plus className="h-3 w-3" />
              {!compact && "Add"}
            </button>
          )}
        </>
      )}

      {/* Limit indicator */}
      {editable && atLimit && (
        <span className="text-xs text-warning-text">
          {maxWatchlistSize < Infinity ? `${watchlist?.length}/${maxWatchlistSize} limit` : ""}
        </span>
      )}

      {/* Error */}
      {addSymbol.error && (
        <span className="text-xs text-bearish-text">
          {addSymbol.error instanceof Error ? addSymbol.error.message : "Failed to add"}
        </span>
      )}

      {/* Empty state */}
      {watchlist && watchlist.length === 0 && !showAdd && (
        <span className="text-sm text-text-faint">No symbols yet — click + to add</span>
      )}
    </div>
  );
}
