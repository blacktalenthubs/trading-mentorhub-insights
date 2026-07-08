/** Premarket Gap Board — stocks gapping pre-bell so you can plan before the open.
 *  Two buckets: Clean (large/mega cap) and Momentum (small/mid). Each gapper
 *  shows gap%, premarket volume (liquidity), key levels (PDH/PDL), and a news
 *  catalyst. Tap a row to chart it; add it to your watchlist.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  usePremarketGaps,
  useRefreshPremarketGaps,
  useWatchlist,
  useAddSymbol,
  type PremarketGapEntry,
} from "../api/hooks";
import { Skeleton, SkeletonRow } from "./ui/Skeleton";
import EmptyState from "./ui/EmptyState";
import { Activity, RefreshCw, Plus, Check, Flame, Newspaper } from "lucide-react";

function fmtAge(iso: string | null): string {
  if (!iso) return "never";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`;
}
function gapColor(g: number | null): string {
  if (g == null) return "text-text-faint";
  return g > 0 ? "text-bullish-text" : "text-bearish-text";
}
function fmtGap(g: number | null): string {
  return g == null ? "—" : `${g > 0 ? "+" : ""}${g.toFixed(1)}%`;
}
function fmtVol(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}
function fmtPx(v: number | null): string {
  return v == null ? "—" : `$${v.toFixed(2)}`;
}

function GapRow({ e, owned, onChart, onAdd, adding }: {
  e: PremarketGapEntry; owned: boolean; onChart: () => void; onAdd: () => void; adding: boolean;
}) {
  return (
    <div className="border-b border-border-subtle/30 last:border-b-0 px-4 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <button onClick={onChart} className="text-left min-w-0 flex-1" title={`Chart ${e.symbol}`}>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-primary">{e.symbol}</span>
            <span className={`text-base font-mono font-bold ${gapColor(e.gap_pct)}`}>{fmtGap(e.gap_pct)}</span>
            {e.bucket === "momentum" && (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-semibold text-warning-text bg-warning/10 px-1 py-0.5 rounded" title="Small/mid-cap momentum — higher risk">
                <Flame className="h-2.5 w-2.5" /> momentum
              </span>
            )}
          </div>
          {/* Levels row */}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] font-mono text-text-faint">
            <span className="text-text-muted">{fmtPx(e.pm_last)}</span>
            <span>PMH {fmtPx(e.pm_high)}</span>
            <span>PDH {fmtPx(e.pdh)}</span>
            <span>PDL {fmtPx(e.pdl)}</span>
            <span title="Premarket $-volume (liquidity)">vol {fmtVol(e.pm_dollar_vol)}</span>
          </div>
          {/* Catalyst */}
          {e.catalyst && (
            <div className="mt-1 flex items-start gap-1 text-[11px] text-text-muted">
              <Newspaper className="h-3 w-3 mt-0.5 shrink-0 text-accent/70" />
              <span className="line-clamp-2">{e.catalyst}</span>
            </div>
          )}
        </button>
        <div className="shrink-0">
          {owned ? (
            <span className="inline-flex items-center text-bullish-text" title="On your watchlist"><Check className="h-4 w-4" /></span>
          ) : (
            <button onClick={onAdd} disabled={adding}
              className="p-1 rounded text-accent hover:bg-accent/10 disabled:opacity-50 active:scale-95"
              title={`Add ${e.symbol} to watchlist`}>
              <Plus className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Bucket({ title, items, watchSet, onChart, onAdd, adding }: {
  title: string; items: PremarketGapEntry[]; watchSet: Set<string>;
  onChart: (s: string) => void; onAdd: (s: string) => void; adding: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-2">{title} <span className="text-text-faint">({items.length})</span></h3>
      <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
        {items.map((e) => (
          <GapRow key={e.symbol} e={e} owned={watchSet.has(e.symbol.toUpperCase())}
            onChart={() => onChart(e.symbol)} onAdd={() => onAdd(e.symbol)} adding={adding} />
        ))}
      </div>
    </div>
  );
}

/** Gap-and-Go Queue card — a top-3 quality-ranked gapper as a rich card: rank +
 *  symbol + gap% + quality, catalyst, derived flags, a Watch/Go/Stop/Invalidation
 *  plan grid (from PDH/PDL/prior-close), and the pipeline outcomes (a queued name IS
 *  in the 8:30 notes, on Today, and armed). Levels derived; no new backend. */
function QueueCard({ e, onChart }: { e: PremarketGapEntry; onChart: () => void }) {
  const abovePdh = e.pm_last != null && e.pdh != null && e.pm_last > e.pdh;
  const flags: { t: string; cls: "ok" | "info" | "warn" }[] = [];
  if (e.pm_dollar_vol != null) flags.push({ t: `✓ ${fmtVol(e.pm_dollar_vol)} PM vol`, cls: "ok" });
  flags.push(abovePdh ? { t: "✓ above PDH", cls: "ok" } : { t: "◔ below PDH — needs reclaim", cls: "warn" });
  if (e.catalyst) flags.push({ t: "✓ catalyst", cls: "ok" });
  if (e.rs != null) flags.push({ t: `RS ${e.rs >= 0 ? "+" : ""}${e.rs}% vs SPY`, cls: e.rs > 0 ? "ok" : "warn" });
  if (e.above_50ma) flags.push({ t: "✓ above 50-MA (accumulation)", cls: "ok" });
  if (e.is_ai) flags.push({ t: "AI space", cls: "info" });
  if (e.on_watchlist) flags.push({ t: "★ on watchlist", cls: "warn" });
  if (e.bucket === "momentum") flags.push({ t: "⚠ momentum — half size", cls: "warn" });
  const fcls = (c: "ok" | "info" | "warn") =>
    c === "ok" ? "bg-bullish/10 text-bullish-text border-bullish/25"
      : c === "info" ? "bg-accent/10 text-accent border-accent/25"
      : "bg-warning/10 text-warning-text border-warning/25";
  const Cell = ({ k, v, tone }: { k: string; v: string; tone: string }) => (
    <div className="bg-surface-1 px-2 py-1.5">
      <div className="font-mono text-[8px] uppercase tracking-wide text-text-faint">{k}</div>
      <div className={`font-mono text-[12.5px] font-bold ${tone}`}>{v}</div>
    </div>
  );
  return (
    <button
      onClick={onChart}
      className={`overflow-hidden rounded-xl border text-left transition-colors hover:border-warning/60 ${e.queue_rank === 1 ? "border-warning/45 bg-warning/[0.06]" : "border-border-subtle bg-surface-1"}`}
    >
      <div className="flex items-center gap-2 border-b border-border-subtle/60 px-3 py-2.5">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-warning text-[11px] font-bold text-surface-0">{e.queue_rank}</span>
        <span className="font-mono text-[17px] font-bold text-text-primary">{e.symbol}</span>
        <span className={`font-mono text-[13px] font-bold ${gapColor(e.gap_pct)}`}>{fmtGap(e.gap_pct)}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-text-faint">Quality <b className="text-[13px] text-warning-text">{e.quality_score ?? "—"}</b></span>
      </div>
      <div className="space-y-2.5 p-3">
        {e.catalyst && <p className="line-clamp-2 text-[11.5px] text-text-muted">{e.catalyst}</p>}
        <div className="flex flex-wrap gap-1">
          {flags.map((f, i) => <span key={i} className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold ${fcls(f.cls)}`}>{f.t}</span>)}
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-surface-3 sm:grid-cols-4">
          <Cell k="Watch" v={fmtPx(e.pm_last)} tone="text-text-secondary" />
          <Cell k="Go over" v={fmtPx(e.pdh)} tone="text-warning-text" />
          <Cell k="Stop" v={fmtPx(e.pdl)} tone="text-bearish-text" />
          <Cell k="Invalid" v={fmtPx(e.prior_close)} tone="text-text-muted" />
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[9.5px] text-text-faint">
          <span>📨 in 8:30 notes <b className="text-bullish-text">✓</b></span>
          <span>☀️ on Today <b className="text-bullish-text">✓</b></span>
          <span>🔔 alert armed <b className="text-bullish-text">✓</b></span>
        </div>
      </div>
    </button>
  );
}

/** Morning-notes preview — renders the 8:30 ET Telegram block the queue produces,
 *  so you can see exactly what gets sent. Built from the same queue entries. */
function NotesPreview({ queue }: { queue: PremarketGapEntry[] }) {
  if (queue.length === 0) return null;
  const px = (v: number | null) => (v == null ? "—" : v.toFixed(2));
  const lines = queue.map((e, i) => {
    const abovePdh = e.pm_last != null && e.pdh != null && e.pm_last > e.pdh;
    const trig = abovePdh ? "go on 5m close above w/ 2× vol" : `needs PDH reclaim ${px(e.pdh)}`;
    const cat = e.catalyst ? ` — ${e.catalyst}` : "";
    const mom = e.bucket === "momentum" ? " · momentum, half size" : "";
    return `${i + 1}. ${e.symbol} ${fmtGap(e.gap_pct)}${cat}${mom}\n   watch ${px(e.pm_last)} · ${trig} · stop ${px(e.pdl)}`;
  });
  const text = `🚀 GAP & GO — priority at the open\n\n${lines.join("\n\n")}\n\nGap fill below prior close = stand down.`;
  return (
    <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-1">
      <div className="flex items-center justify-between border-b border-border-subtle px-3.5 py-2">
        <span className="text-[12px] font-bold text-text-secondary">📨 Morning notes — 8:30 ET</span>
        <span className="text-[10px] text-text-faint">Telegram preview</span>
      </div>
      <pre className="whitespace-pre-wrap px-3.5 py-3 font-mono text-[11px] leading-relaxed text-text-secondary">{text}</pre>
      <div className="border-t border-border-subtle px-3.5 py-2 text-[10px] text-text-faint">Appended to the Premarket Heat brief; the top 3 also arm gap-and-go alerts.</div>
    </div>
  );
}

export default function PremarketGapsTab() {
  const { data, isLoading, error } = usePremarketGaps();
  const refresh = useRefreshPremarketGaps();
  const { data: watchlist } = useWatchlist();
  const addSymbol = useAddSymbol();
  const navigate = useNavigate();

  const watchSet = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );

  const entries = data?.entries ?? [];
  const [sortBy, setSortBy] = useState<"recommended" | "volume" | "gap">("recommended");
  const sortFns = {
    recommended: (a: PremarketGapEntry, b: PremarketGapEntry) => (b.quality_score ?? 0) - (a.quality_score ?? 0) || (b.pm_dollar_vol ?? 0) - (a.pm_dollar_vol ?? 0),
    volume: (a: PremarketGapEntry, b: PremarketGapEntry) => (b.pm_dollar_vol ?? 0) - (a.pm_dollar_vol ?? 0),
    gap: (a: PremarketGapEntry, b: PremarketGapEntry) => (b.gap_pct ?? 0) - (a.gap_pct ?? 0),
  };
  const clean = entries.filter((e) => e.bucket === "clean").slice().sort(sortFns[sortBy]);
  const momentum = entries.filter((e) => e.bucket === "momentum").slice().sort(sortFns[sortBy]);
  const queue = entries.filter((e) => e.queue_rank != null).sort((a, b) => (a.queue_rank ?? 9) - (b.queue_rank ?? 9)).slice(0, 3);

  function onChart(s: string) { navigate(`/trading?symbol=${encodeURIComponent(s)}`); }

  if (isLoading) {
    return <div className="space-y-3"><Skeleton w={200} h={16} /><SkeletonRow count={6} h={56} /></div>;
  }
  if (error) {
    return <div className="text-center py-12 text-sm text-bearish-text">Failed to load premarket gaps.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between text-xs text-text-faint">
        <span>
          {entries.length} gappers · gap ≥ 2% with real premarket volume
          {data?.captured_at && <> · {fmtAge(data.captured_at)}{data.stale && " · stale"}</>}
        </span>
        <div className="flex items-center gap-2">
          <div className="flex items-center overflow-hidden rounded-full border border-border-subtle text-[10px] font-semibold">
            {(["recommended", "volume", "gap"] as const).map((k, i) => (
              <button
                key={k}
                onClick={() => setSortBy(k)}
                title={k === "recommended" ? "Volume + relative strength + structure weighted" : k === "volume" ? "Biggest premarket $-volume first" : "Biggest gap % first"}
                className={`px-2.5 py-1 transition-colors ${i > 0 ? "border-l border-border-subtle" : ""} ${sortBy === k ? "bg-accent text-bg-base" : "bg-surface-1 text-text-muted hover:bg-surface-2"}`}
              >
                {k === "recommended" ? "Recommended" : k === "volume" ? "Volume" : "Gap %"}
              </button>
            ))}
          </div>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="flex items-center gap-1.5 rounded-full bg-accent/15 text-accent px-3 py-1.5 hover:bg-accent/25 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Scanning…" : "Scan now"}
          </button>
        </div>
      </div>

      {entries.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No premarket gappers yet"
          hint="The scan runs every 15 min from 7:00–9:45 AM ET and lists stocks gapping with real premarket volume. Outside that window it'll be empty — or tap 'Scan now'."
        />
      ) : (
        <div className="space-y-5">
          {queue.length > 0 && (
            <div className="space-y-2.5">
              <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-xl border border-warning/30 bg-warning/5 px-3.5 py-2.5 text-[11px] text-text-muted">
                <span className="font-bold text-warning-text">🚀 Gap &amp; Go Queue</span>
                <span>→ top 3 by quality →</span>
                <span>📨 8:30 notes <b className="text-bullish-text">sent</b> →</span>
                <span>☀️ Today's tab <b className="text-bullish-text">published</b> →</span>
                <span>🔔 alerts <b className="text-bullish-text">armed</b> (5m close over trigger · 2× vol)</span>
              </div>
              <div className="grid grid-cols-1 gap-2.5 lg:grid-cols-3">
                {queue.map((e) => <QueueCard key={e.symbol} e={e} onChart={() => onChart(e.symbol)} />)}
              </div>
              <NotesPreview queue={queue} />
            </div>
          )}
          <Bucket title="Clean gaps" items={clean} watchSet={watchSet} onChart={onChart} onAdd={(s) => addSymbol.mutate(s)} adding={addSymbol.isPending} />
          <Bucket title="Momentum gappers" items={momentum} watchSet={watchSet} onChart={onChart} onAdd={(s) => addSymbol.mutate(s)} adding={addSymbol.isPending} />
        </div>
      )}

      <p className="text-[11px] text-text-faint leading-relaxed">
        Gap % is premarket vs prior close. <span className="text-text-secondary">PMH</span> = premarket high,
        <span className="text-text-secondary"> PDH/PDL</span> = prior day high/low — your plan levels. Prep before
        the bell, then watch whether the gap <em>holds</em> the open (gap-and-go) or fills.
        <span className="text-warning-text"> Momentum</span> names move more but trap more — mind the volume.
      </p>
    </div>
  );
}
