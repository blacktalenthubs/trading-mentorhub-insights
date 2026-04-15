/** Best Setups of the Day — AI-ranked watchlist scan (Spec 40). */

import { useBestSetups } from "../api/hooks";
import { Sparkles, RefreshCw, ArrowUp, ArrowDown } from "lucide-react";
import { useState } from "react";

export default function BestSetupsCard({
  onSelectSymbol,
}: {
  onSelectSymbol?: (symbol: string) => void;
}) {
  const [triggered, setTriggered] = useState(false);
  const { data, isLoading, isFetching, refetch, error } = useBestSetups(triggered);

  function handleRun() {
    setTriggered(true);
    if (triggered) refetch();  // already enabled → force refresh
  }

  const err = error as { message?: string; detail?: { message?: string } } | null;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
          <span className="text-[11px] font-bold text-text-primary">Best Setups Today</span>
        </div>
        <button
          onClick={handleRun}
          disabled={isFetching}
          className="text-[10px] px-2.5 py-1 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center gap-1"
        >
          {isFetching ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          {triggered ? "Refresh" : "Run scan"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {!triggered && (
          <div className="text-center py-8 text-xs text-text-muted">
            <p>AI scans your watchlist and ranks best setups for today</p>
            <p className="text-[10px] text-text-faint mt-1">
              Click Run scan to start
            </p>
          </div>
        )}

        {triggered && isLoading && (
          <div className="text-center py-8 text-xs text-text-muted">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto mb-2 text-accent" />
            Scanning watchlist…
          </div>
        )}

        {err && (
          <div className="text-center py-4 text-xs text-red-400">
            {err.detail?.message || err.message || "Failed to scan"}
          </div>
        )}

        {data && !isLoading && (
          <>
            <div className="text-[10px] text-text-faint mb-1">
              {data.setups_found} setup{data.setups_found !== 1 ? "s" : ""} ·
              {" "}watchlist {data.watchlist_size}
              {data.error && <span className="text-red-400 ml-2">({data.error})</span>}
            </div>

            {data.picks.length === 0 && (
              <div className="text-center py-6 text-xs text-text-muted">
                No qualifying setups right now. AI didn't see a clear edge.
              </div>
            )}

            {data.picks.map((p, i) => {
              const isLong = p.direction === "LONG";
              return (
                <div
                  key={`${p.symbol}-${i}`}
                  className="rounded-lg border border-border-subtle bg-surface-1 p-3 hover:bg-surface-2/50 transition-colors cursor-pointer"
                  onClick={() => onSelectSymbol?.(p.symbol)}
                >
                  <div className="flex items-start justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-text-faint font-mono">#{i + 1}</span>
                      <span className="text-sm font-bold text-text-primary">{p.symbol}</span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5 ${
                          isLong
                            ? "bg-bullish/15 text-bullish-text border border-bullish/25"
                            : "bg-bearish/15 text-bearish-text border border-bearish/25"
                        }`}
                      >
                        {isLong ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />}
                        {p.direction}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-bold text-accent">
                        R:R {p.rr_ratio.toFixed(1)}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
                          p.conviction === "HIGH"
                            ? "bg-emerald-500/15 text-emerald-400"
                            : p.conviction === "MEDIUM"
                            ? "bg-yellow-500/15 text-yellow-400"
                            : "bg-text-muted/15 text-text-muted"
                        }`}
                      >
                        {p.conviction}
                      </span>
                    </div>
                  </div>

                  <div className="text-[11px] text-text-secondary mb-2">
                    {p.setup_type}
                  </div>

                  <div className="grid grid-cols-4 gap-2 text-[10px] mb-2">
                    <div>
                      <div className="text-text-faint">Entry</div>
                      <div className="font-mono text-text-primary font-bold">${p.entry.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">Stop</div>
                      <div className="font-mono text-bearish-text">${p.stop.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">T1</div>
                      <div className="font-mono text-bullish-text">${p.t1.toFixed(2)}</div>
                    </div>
                    <div>
                      <div className="text-text-faint">T2</div>
                      <div className="font-mono text-text-secondary">
                        {p.t2 ? `$${p.t2.toFixed(2)}` : "—"}
                      </div>
                    </div>
                  </div>

                  <div className="text-[10px] text-text-muted italic border-t border-border-subtle/50 pt-2">
                    {p.why_now}
                  </div>

                  {p.confluence.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {p.confluence.map((c, j) => (
                        <span key={j} className="text-[9px] bg-accent/10 text-accent px-1.5 py-0.5 rounded">
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {data.skipped && data.skipped.length > 0 && (
              <details className="text-[10px] text-text-faint mt-3">
                <summary className="cursor-pointer hover:text-text-muted">
                  Skipped {data.skipped.length} symbol{data.skipped.length !== 1 ? "s" : ""}
                </summary>
                <ul className="mt-1 space-y-0.5 pl-2">
                  {data.skipped.map((s, i) => (
                    <li key={i} className="truncate">
                      <span className="font-mono text-text-muted">{s.symbol}</span> — {s.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  );
}
