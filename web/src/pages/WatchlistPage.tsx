/** Watchlist management — grouped view with collapsible categories. */

import { useMemo, useState } from "react";
import {
  useWatchlist,
  useAddSymbol,
  useRemoveSymbol,
  useWatchlistGroups,
  useSeedDefaultGroups,
  useDeleteGroup,
  useMoveItem,
  type WatchlistItem,
  type WatchlistGroup,
} from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import Card from "../components/ui/Card";
import { Plus, Loader2, Trash2, Star, ChevronDown, ChevronRight, Sparkles, FolderX } from "lucide-react";

const UNGROUPED_KEY = -1;

export default function WatchlistPage() {
  const { data: watchlist, isLoading } = useWatchlist();
  const { data: groups } = useWatchlistGroups();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const seedDefaults = useSeedDefaultGroups();
  const deleteGroup = useDeleteGroup();
  const moveItem = useMoveItem();
  const { maxWatchlistSize, isPro } = useFeatureGate();
  const [input, setInput] = useState("");
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());

  const count = watchlist?.length ?? 0;
  const atLimit = count >= maxWatchlistSize;
  const hasGroups = (groups?.length ?? 0) > 0;

  // Bucket items by group_id (null → UNGROUPED_KEY).
  const byGroup = useMemo(() => {
    const map = new Map<number, WatchlistItem[]>();
    for (const item of watchlist ?? []) {
      const key = item.group_id ?? UNGROUPED_KEY;
      const list = map.get(key) ?? [];
      list.push(item);
      map.set(key, list);
    }
    return map;
  }, [watchlist]);

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = input.trim().toUpperCase();
    if (!sym) return;
    addSymbol.mutate(sym, { onSuccess: () => setInput("") });
  }

  function toggleCollapse(groupId: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }

  // Build display order: groups by sort_order first, then ungrouped last.
  const displayGroups: Array<WatchlistGroup | { id: typeof UNGROUPED_KEY; name: string; color: string; sort_order: number }> = useMemo(() => {
    const sorted = [...(groups ?? [])].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    const ungroupedItems = byGroup.get(UNGROUPED_KEY) ?? [];
    if (ungroupedItems.length > 0 || sorted.length === 0) {
      return [
        ...sorted,
        { id: UNGROUPED_KEY, name: "Ungrouped", color: "", sort_order: 9999 },
      ];
    }
    return sorted;
  }, [groups, byGroup]);

  return (
    <div className="h-full overflow-y-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Star className="h-5 w-5 text-accent" />
          <h1 className="font-display text-2xl font-bold">Watchlist</h1>
          <span className="rounded-full bg-surface-4 px-2.5 py-1 text-xs font-medium text-text-muted">
            {count}{maxWatchlistSize < Infinity ? ` / ${maxWatchlistSize}` : ""}
          </span>
        </div>
        {!hasGroups && (
          <button
            onClick={() => seedDefaults.mutate()}
            disabled={seedDefaults.isPending}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40 active:scale-95"
          >
            {seedDefaults.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5" />
            )}
            Seed Default Groups
          </button>
        )}
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

      {isLoading && (
        <div className="flex items-center gap-2 py-8">
          <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          <span className="text-sm text-text-muted">Loading watchlist...</span>
        </div>
      )}

      {/* Grouped sections */}
      {watchlist && watchlist.length > 0 && (
        <div className="space-y-3">
          {displayGroups.map((g) => {
            const items = byGroup.get(g.id) ?? [];
            if (items.length === 0 && g.id !== UNGROUPED_KEY) return null;
            const isCollapsed = collapsed.has(g.id);
            const isUngrouped = g.id === UNGROUPED_KEY;
            return (
              <Card key={g.id} padding="none">
                <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2.5">
                  <button
                    onClick={() => toggleCollapse(g.id)}
                    className="flex items-center gap-2 text-sm font-semibold text-text-primary transition-colors hover:text-accent"
                  >
                    {isCollapsed ? (
                      <ChevronRight className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                    {g.color && !isUngrouped && (
                      <span
                        className="h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: g.color }}
                      />
                    )}
                    <span>{g.name}</span>
                    <span className="rounded-full bg-surface-4 px-2 py-0.5 text-xs font-normal text-text-muted">
                      {items.length}
                    </span>
                  </button>
                  {!isUngrouped && (
                    <button
                      onClick={() => {
                        if (confirm(`Delete group "${g.name}"? Items will move to Ungrouped.`)) {
                          deleteGroup.mutate(g.id);
                        }
                      }}
                      title="Delete group (items move to Ungrouped)"
                      className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bearish-muted hover:text-bearish-text"
                    >
                      <FolderX className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>

                {!isCollapsed && items.length > 0 && (
                  <div className="divide-y divide-border-subtle">
                    {items.map((item, i) => (
                      <div
                        key={item.id}
                        className="flex items-center justify-between px-4 py-2.5 transition-colors hover:bg-surface-3/50"
                      >
                        <div className="flex items-center gap-4">
                          <span className="w-6 text-center text-xs text-text-faint">{i + 1}</span>
                          <span className="text-sm font-semibold text-text-primary">{item.symbol}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Move to group dropdown — small, only shown when groups exist */}
                          {hasGroups && (
                            <select
                              value={item.group_id ?? ""}
                              onChange={(e) => {
                                const val = e.target.value;
                                moveItem.mutate({
                                  itemId: item.id,
                                  groupId: val === "" ? null : Number(val),
                                });
                              }}
                              className="rounded-md border border-border-subtle bg-surface-3 px-2 py-1 text-xs text-text-muted focus:border-accent focus:outline-none"
                              title="Move to group"
                            >
                              <option value="">Ungrouped</option>
                              {groups?.map((grp) => (
                                <option key={grp.id} value={grp.id}>{grp.name}</option>
                              ))}
                            </select>
                          )}
                          <button
                            onClick={() => removeSymbol.mutate(item.symbol)}
                            disabled={removeSymbol.isPending}
                            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:bg-bearish-muted hover:text-bearish-text active:scale-95"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {!isCollapsed && items.length === 0 && isUngrouped && (
                  <div className="px-4 py-3 text-xs text-text-faint">
                    All your symbols are in groups. Add new ones above or move items here.
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {watchlist && watchlist.length === 0 && !isLoading && (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <Star className="h-10 w-10 text-text-faint" />
          <p className="text-text-muted">Your watchlist is empty</p>
          <p className="text-sm text-text-faint">Add ticker symbols above, or click Seed Default Groups for a curated start.</p>
          <button
            onClick={() => seedDefaults.mutate()}
            disabled={seedDefaults.isPending}
            className="mt-2 flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-40 active:scale-95"
          >
            {seedDefaults.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Seed 7 default groups + 27 tickers
          </button>
        </div>
      )}
    </div>
  );
}
