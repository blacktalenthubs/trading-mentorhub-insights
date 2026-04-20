/** Best Setups — on-demand proximity-based entry finder (day + swing). */

import { useBestSetups, usePinBestSetupAlert, type EntryCandidate } from "../api/hooks";
import { toast } from "./Toast";
import { Sparkles, RefreshCw, ArrowUp, ArrowDown, Zap, Calendar, Bell, Copy, BarChart3 } from "lucide-react";
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
    if (triggered) refetch();
  }

  const err = error as { message?: string; detail?: { message?: string } } | null;

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5 text-accent" />
          <span className="text-[11px] font-bold text-text-primary">Best Setups</span>
        </div>
        <button
          onClick={handleRun}
          disabled={isFetching}
          className="text-[10px] px-2.5 py-1 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center gap-1"
        >
          <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin" : ""}`} />
          {triggered ? "Refresh" : "Analyze watchlist"}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {!triggered && (
          <div className="text-center py-8 text-xs text-text-muted">
            <p>AI scans your watchlist for symbols near key entry levels</p>
            <p className="text-[10px] text-text-faint mt-1">
              Click Analyze watchlist to start
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
              {data.day_trade_picks.length} day · {data.swing_trade_picks.length} swing
              {" "}· watchlist {data.watchlist_size}
              {data.error && <span className="text-red-400 ml-2">({data.error})</span>}
            </div>

            <SectionBlock
              label="Day Trade Candidates"
              icon={<Zap className="h-3 w-3 text-yellow-400" />}
              picks={data.day_trade_picks}
              emptyHint="No symbols near intraday levels right now."
              onSelectSymbol={onSelectSymbol}
            />

            <SectionBlock
              label="Swing Trade Candidates"
              icon={<Calendar className="h-3 w-3 text-accent" />}
              picks={data.swing_trade_picks}
              emptyHint="No symbols near daily levels right now."
              onSelectSymbol={onSelectSymbol}
            />

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

function SectionBlock({
  label,
  icon,
  picks,
  emptyHint,
  onSelectSymbol,
}: {
  label: string;
  icon: React.ReactNode;
  picks: EntryCandidate[];
  emptyHint: string;
  onSelectSymbol?: (symbol: string) => void;
}) {
  return (
    <div className="space-y-2 mb-3">
      <div className="flex items-center gap-1.5 text-[10px] font-bold text-text-secondary uppercase tracking-wide">
        {icon}
        <span>{label}</span>
        <span className="text-text-faint font-normal">({picks.length})</span>
      </div>

      {picks.length === 0 ? (
        <div className="text-center py-3 text-[11px] text-text-muted italic">
          {emptyHint}
        </div>
      ) : (
        picks.map((p, i) => <PickCard key={`${p.symbol}-${i}`} pick={p} onSelectSymbol={onSelectSymbol} />)
      )}
    </div>
  );
}

function PickCard({
  pick,
  onSelectSymbol,
}: {
  pick: EntryCandidate;
  onSelectSymbol?: (symbol: string) => void;
}) {
  const isLong = pick.direction === "LONG";
  const fmt = (v: number | null) => (v != null ? `$${v.toFixed(2)}` : "—");
  const pinAlert = usePinBestSetupAlert();

  function handleCopy(e: React.MouseEvent) {
    e.stopPropagation();
    const parts = [
      `${pick.symbol} ${pick.direction}`,
      `Entry $${pick.entry.toFixed(2)}`,
      pick.stop != null ? `Stop $${pick.stop.toFixed(2)}` : null,
      pick.t1 != null ? `T1 $${pick.t1.toFixed(2)}` : null,
      pick.t2 != null ? `T2 $${pick.t2.toFixed(2)}` : null,
    ].filter(Boolean);
    navigator.clipboard.writeText(parts.join(" · ")).then(
      () => toast.success("Copied to clipboard"),
      () => toast.error("Copy failed"),
    );
  }

  function handlePinAlert(e: React.MouseEvent) {
    e.stopPropagation();
    pinAlert.mutate({
      symbol: pick.symbol,
      timeframe: pick.timeframe,
      direction: pick.direction,
      setup_type: pick.setup_type,
      entry: pick.entry,
      stop: pick.stop,
      t1: pick.t1,
      t2: pick.t2,
      conviction: pick.conviction,
      why_now: pick.why_now,
      current_price: pick.current_price,
    });
  }

  function handleChart(e: React.MouseEvent) {
    e.stopPropagation();
    onSelectSymbol?.(pick.symbol);
  }

  return (
    <div
      className="rounded-lg border border-border-subtle bg-surface-1 p-3 hover:bg-surface-2/50 transition-colors cursor-pointer"
      onClick={() => onSelectSymbol?.(pick.symbol)}
    >
      <div className="flex items-start justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-text-primary">{pick.symbol}</span>
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5 ${
              isLong
                ? "bg-bullish/15 text-bullish-text border border-bullish/25"
                : "bg-bearish/15 text-bearish-text border border-bearish/25"
            }`}
          >
            {isLong ? <ArrowUp className="h-2.5 w-2.5" /> : <ArrowDown className="h-2.5 w-2.5" />}
            {pick.direction}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-bold text-accent">
            {pick.distance_to_entry_pct.toFixed(1)}% away
          </span>
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${
              pick.conviction === "HIGH"
                ? "bg-emerald-500/15 text-emerald-400"
                : pick.conviction === "MEDIUM"
                ? "bg-yellow-500/15 text-yellow-400"
                : "bg-text-muted/15 text-text-muted"
            }`}
          >
            {pick.conviction}
          </span>
        </div>
      </div>

      <div className="text-[11px] text-text-secondary mb-2">
        {pick.setup_type}
      </div>

      <div className="grid grid-cols-4 gap-2 text-[10px] mb-2">
        <div>
          <div className="text-text-faint">Entry</div>
          <div className="font-mono text-text-primary font-bold">{fmt(pick.entry)}</div>
        </div>
        <div>
          <div className="text-text-faint">Stop</div>
          <div className="font-mono text-bearish-text">{fmt(pick.stop)}</div>
        </div>
        <div>
          <div className="text-text-faint">T1</div>
          <div className="font-mono text-bullish-text">{fmt(pick.t1)}</div>
        </div>
        <div>
          <div className="text-text-faint">T2</div>
          <div className="font-mono text-text-secondary">{fmt(pick.t2)}</div>
        </div>
      </div>

      {pick.why_now && (
        <div className="text-[10px] text-text-muted italic border-t border-border-subtle/50 pt-2">
          {pick.why_now}
        </div>
      )}

      {pick.confluence.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {pick.confluence.map((c, j) => (
            <span key={j} className="text-[9px] bg-accent/10 text-accent px-1.5 py-0.5 rounded">
              {c}
            </span>
          ))}
        </div>
      )}

      <div className="mt-2 pt-2 border-t border-border-subtle/50 flex items-center gap-1">
        <button
          onClick={handlePinAlert}
          disabled={pinAlert.isPending}
          className="flex-1 text-[10px] px-2 py-1 rounded bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center justify-center gap-1"
          title="Send this setup to Telegram with Took/Skip/Exit buttons"
        >
          <Bell className="h-3 w-3" />
          {pinAlert.isPending ? "Sending…" : "Alert"}
        </button>
        <button
          onClick={handleChart}
          className="flex-1 text-[10px] px-2 py-1 rounded bg-surface-2 text-text-secondary hover:bg-surface-3 transition-colors flex items-center justify-center gap-1"
          title="Open symbol in main chart"
        >
          <BarChart3 className="h-3 w-3" />
          Chart
        </button>
        <button
          onClick={handleCopy}
          className="flex-1 text-[10px] px-2 py-1 rounded bg-surface-2 text-text-secondary hover:bg-surface-3 transition-colors flex items-center justify-center gap-1"
          title="Copy setup levels to clipboard"
        >
          <Copy className="h-3 w-3" />
          Copy
        </button>
      </div>
    </div>
  );
}
