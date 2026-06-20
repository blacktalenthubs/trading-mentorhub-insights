/** Conviction screener — analyst-backed long-term uptrends.
 *  Finds mid-cap AI / chips / disruptive-tech names that pair a STRONG analyst
 *  rating with a persistent uptrend above the 50-day MA (the ZETA/NBIS profile).
 *  Output is readable by any user; running a fresh scan is Pro-gated.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Gem, RefreshCw, History, Plus, Check, Layers } from "lucide-react";
import {
  useConviction, useConvictionHistory, useRefreshConviction, useSyncConvictionWatchlist,
  useAddSymbol, useWatchlist,
  useWeeklyStage, useRefreshWeeklyStage,
} from "../api/hooks";
import { useFeatureGate } from "../hooks/useFeatureGate";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";
import type { ConvictionEntry, WeeklyStageEntry } from "./InPlay.types";

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

function fmtCap(n: number | null): string {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}

/** Analyst consensus → label + color. recommendationMean: 1=Strong Buy … 5=Sell. */
function ratingMeta(rec: number | null) {
  if (rec == null) return { label: "—", cls: "text-text-faint" };
  if (rec <= 1.5) return { label: "Strong Buy", cls: "text-bullish-text" };
  if (rec <= 2.0) return { label: "Buy", cls: "text-bullish-text" };
  if (rec <= 2.5) return { label: "Buy/Hold", cls: "text-amber-400" };
  return { label: "Hold", cls: "text-text-muted" };
}

function AnalystCell({ r }: { r: ConvictionEntry }) {
  const m = ratingMeta(r.rec_mean);
  return (
    <span className="flex flex-col leading-tight" title={r.rec_mean != null ? `Consensus ${r.rec_mean.toFixed(2)} (1=Strong Buy…5=Sell) from ${r.num_analysts ?? "?"} analysts` : "No analyst coverage"}>
      <span className={`text-xs font-semibold ${m.cls}`}>{m.label}</span>
      {r.num_analysts != null && <span className="text-[10px] text-text-faint">{r.num_analysts} analysts</span>}
    </span>
  );
}

/** How persistently price has held above its 50-day MA + the trend structure. */
function TrendCell({ r }: { r: ConvictionEntry }) {
  const strong = r.pct_days_above_50 >= 80;
  return (
    <span className="flex flex-col leading-tight" title="% of the last 60 sessions the close held above the 50-day MA">
      <span className={`text-xs font-mono ${strong ? "text-bullish-text" : "text-text-secondary"}`}>{r.pct_days_above_50.toFixed(0)}%</span>
      {r.ma_stacked && <span className="text-[10px] text-accent">50&gt;200 ↑</span>}
    </span>
  );
}

/** Add-to-watchlist control. A role="button" span (NOT a <button>) so it's valid
 *  nested inside ScreenerTable's mobile card, which is itself a <button>; stops
 *  propagation so tapping it doesn't also open the chart. */
function AddButton({ owned, onAdd, label }: { owned: boolean; onAdd: () => void; label: string }) {
  if (owned) {
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-md text-bullish-text" title="On your watchlist">
        <Check className="h-4 w-4" />
      </span>
    );
  }
  return (
    <span
      role="button"
      tabIndex={0}
      title={label}
      onClick={(e) => { e.stopPropagation(); onAdd(); }}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); onAdd(); } }}
      className="inline-flex h-7 w-7 cursor-pointer items-center justify-center rounded-md bg-accent/15 text-accent transition-colors hover:bg-accent/25 active:scale-90"
    >
      <Plus className="h-4 w-4" />
    </span>
  );
}

const THEME_ORDER = ["AI Chips", "Semicap", "AI Software", "AI Infra", "AI Optics", "Disruptive"];

/** Bucket → color + label. watch = amber (early), own = green (confirmed), add = blue (pullback). */
const BUCKET_META: Record<string, { label: string; cls: string }> = {
  watch: { label: "WATCH", cls: "bg-amber-400/15 text-amber-400 border-amber-400/30" },
  own: { label: "OWN", cls: "bg-bullish-bg text-bullish-text border-bullish-text/30" },
  add: { label: "ADD", cls: "bg-accent/15 text-accent border-accent/30" },
};

const STAGE_CLS: Record<number, string> = {
  1: "text-text-muted",
  2: "text-bullish-text",
  3: "text-amber-400",
  4: "text-bearish-text",
};

function BucketBadge({ bucket }: { bucket: string }) {
  const m = BUCKET_META[bucket] ?? { label: bucket.toUpperCase(), cls: "bg-surface-3 text-text-muted border-border-subtle" };
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${m.cls}`}>{m.label}</span>
  );
}

const BUCKET_RANK: Record<string, number> = { watch: 3, own: 2, add: 1 };

export function WeeklyStageView() {
  const navigate = useNavigate();
  const { data, isLoading, isError } = useWeeklyStage();
  const refresh = useRefreshWeeklyStage();
  const { isPro } = useFeatureGate();

  const { data: watchlist } = useWatchlist();
  const addSym = useAddSymbol();
  const owned = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );
  const isOwned = (s: string) => owned.has(s.toUpperCase());
  const addToWatchlist = (s: string) => { if (!isOwned(s)) addSym.mutate(s); };

  const [bucket, setBucket] = useState<string>("All");
  const allRows = data?.entries ?? [];
  const rows = bucket === "All" ? allRows : allRows.filter((r) => r.bucket === bucket);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const buckets = useMemo(() => {
    const present = new Set(allRows.map((r) => r.bucket));
    return ["watch", "own", "add"].filter((b) => present.has(b as WeeklyStageEntry["bucket"]));
  }, [allRows]);

  // decision-first summary — lead with the answer (where to look), like Today/Declined/Strategy
  const watchRows = allRows.filter((r) => r.bucket === "watch");
  const ownCount = allRows.filter((r) => r.bucket === "own").length;
  const addCount = allRows.filter((r) => r.bucket === "add").length;
  const watchNames = watchRows.slice(0, 6).map((r) => r.symbol);

  const distCls = (d: number) => (d >= 0 ? "text-bullish-text" : "text-bearish-text");

  const columns: Column<WeeklyStageEntry>[] = [
    { key: "bucket", label: "Bucket", align: "left", cls: "w-16", value: (r) => BUCKET_RANK[r.bucket] ?? 0, render: (r) => <BucketBadge bucket={r.bucket} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => <span className="font-bold text-text-primary">{r.symbol}</span> },
    { key: "stage", label: "Stage", align: "left", value: (r) => r.stage, render: (r) => <span className={`text-xs font-semibold ${STAGE_CLS[r.stage] ?? "text-text-secondary"}`}>{r.stage_label}</span> },
    { key: "ma", label: "30wMA", align: "right", cls: "hidden sm:table-cell", value: (r) => r.ma, render: (r) => <span className="font-mono text-text-secondary">{money(r.ma)}</span> },
    { key: "slope", label: "MA slope", align: "right", cls: "hidden md:table-cell", value: (r) => r.slope_pct, render: (r) => <span className={`font-mono ${r.slope_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.slope_pct >= 0 ? "+" : ""}{r.slope_pct.toFixed(1)}%</span> },
    { key: "price", label: "Price", align: "right", value: (r) => r.price, render: (r) => <span className="font-mono text-text-primary">{money(r.price)}</span> },
    { key: "dist", label: "vs MA", align: "right", value: (r) => r.dist_vs_ma_pct, render: (r) => <span className={`font-mono ${distCls(r.dist_vs_ma_pct)}`}>{r.dist_vs_ma_pct >= 0 ? "+" : ""}{r.dist_vs_ma_pct.toFixed(1)}%</span> },
    { key: "add", label: "", align: "right", cls: "w-10", render: (r) => <AddButton owned={isOwned(r.symbol)} onAdd={() => addToWatchlist(r.symbol)} label={`Add ${r.symbol} to watchlist`} /> },
  ];

  const pill = "text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-3 text-text-muted";
  const mobileRow = (r: WeeklyStageEntry) => (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <BucketBadge bucket={r.bucket} />
          <span className="text-[15px] font-bold text-text-primary">{r.symbol}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-sm text-text-primary">{money(r.price)}</span>
          <AddButton owned={isOwned(r.symbol)} onAdd={() => addToWatchlist(r.symbol)} label={`Add ${r.symbol} to watchlist`} />
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={`text-xs font-semibold ${STAGE_CLS[r.stage] ?? "text-text-secondary"}`}>{r.stage_label}</span>
        <span className={`font-mono text-[11px] ${distCls(r.dist_vs_ma_pct)}`}>{r.dist_vs_ma_pct >= 0 ? "+" : ""}{r.dist_vs_ma_pct.toFixed(1)}% vs MA</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={pill}>30wMA {money(r.ma)}</span>
        <span className={`${pill} ${r.slope_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>slope {r.slope_pct >= 0 ? "+" : ""}{r.slope_pct.toFixed(1)}%</span>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-5 w-5 text-amber-400" />
          <div>
            <h1 className="text-lg font-bold text-text-primary">Weekly Stage</h1>
            <p className="text-[11px] text-text-muted">
              Weinstein 30-week-MA stage — <span className="text-amber-400 font-semibold">WATCH</span> = basing &amp; turning up (early), <span className="text-bullish-text font-semibold">OWN</span> = confirmed Stage 2, <span className="text-accent font-semibold">ADD</span> = pullback to the rising MA. Refreshed Mondays.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {captured && <span className="text-text-faint">Updated {captured.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
          {isPro && (
            <button
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-400/15 text-amber-400 hover:bg-amber-400/25 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
              {refresh.isPending ? "Scanning…" : "Run scan"}
            </button>
          )}
        </div>
      </div>

      {allRows.length > 0 && (
        <div className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-3.5 text-[13px] text-text-secondary leading-relaxed">
          <span className="font-semibold text-text-primary">Where to look — </span>
          {watchRows.length > 0
            ? <><span className="text-amber-400 font-medium">{watchRows.length} basing &amp; turning up</span> (early watch: {watchNames.join(", ")}{watchRows.length > watchNames.length ? "…" : ""})</>
            : <>nothing in the early-watch bucket right now</>}
          {ownCount > 0 && <> · <span className="text-bullish-text font-medium">{ownCount} confirmed Stage 2</span></>}
          {addCount > 0 && <> · <span className="text-accent font-medium">{addCount} at the rising MA</span></>}.
        </div>
      )}

      {buckets.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {["All", ...buckets].map((b) => (
            <button
              key={b}
              onClick={() => setBucket(b)}
              className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
                bucket === b
                  ? "bg-amber-400/15 text-amber-400 border-amber-400/40"
                  : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-secondary"
              }`}
            >
              {b === "All" ? "All" : (BUCKET_META[b]?.label ?? b)}
            </button>
          ))}
        </div>
      )}

      <ScreenerTable<WeeklyStageEntry>
        rows={rows}
        columns={columns}
        rowKey={(r) => r.symbol}
        onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
        defaultSort={{ key: "bucket", dir: "desc" }}
        mobileRow={mobileRow}
        isLoading={isLoading}
        isError={isError}
        errorText="Couldn't load the weekly-stage screen."
        empty={
          <div className="px-4 py-10 text-center text-sm text-text-muted">
            No weekly-stage candidates in the latest run.
            {isPro && " Tap Run scan to refresh — 30-week-MA stage over the swing universe."}
          </div>
        }
      />

      <p className="text-[11px] text-text-faint leading-relaxed">
        <strong>Weinstein stages</strong> classify a name by its 30-week MA: Stage 1 basing, Stage 2 advancing (own/add), Stage 3 topping, Stage 4 declining. <strong>WATCH</strong> surfaces Stage 1/4 names within ~8% of the MA whose 4-week MA slope is improving — the early turn. Research only — not financial advice.
      </p>
    </div>
  );
}

const PAGE_TABS = [
  { key: "conviction", label: "Conviction" },
  { key: "weekly", label: "Weekly Stage" },
] as const;

/** The full Conviction content — the Conviction screener + Weekly Stage with their toggle.
 *  Exported so it can live as a tab inside Trade Ideas (no page wrapper). */
export function ConvictionTabView() {
  const [view, setView] = useState<"conviction" | "weekly">("conviction");
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5">
        {PAGE_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setView(t.key)}
            className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition-colors ${
              view === t.key
                ? "bg-accent/15 text-accent border-accent/40"
                : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-secondary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {view === "conviction" ? <ConvictionView /> : <WeeklyStageView />}
    </div>
  );
}

export default function ConvictionPage() {
  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5">
        <ConvictionTabView />
      </div>
    </div>
  );
}

function ConvictionView() {
  const navigate = useNavigate();
  const [runId, setRunId] = useState<number | null>(null);
  const [theme, setTheme] = useState<string>("All");

  const { data, isLoading, isError } = useConviction(runId);
  const history = useConvictionHistory();
  const refresh = useRefreshConviction();
  const syncWatchlist = useSyncConvictionWatchlist();
  const { isPro } = useFeatureGate();

  const { data: watchlist } = useWatchlist();
  const addSym = useAddSymbol();
  const owned = useMemo(
    () => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())),
    [watchlist],
  );
  const isOwned = (s: string) => owned.has(s.toUpperCase());
  const addToWatchlist = (s: string) => { if (!isOwned(s)) addSym.mutate(s); };

  const allRows = data?.entries ?? [];
  const rows = theme === "All" ? allRows : allRows.filter((r) => r.theme === theme);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  const themes = useMemo(() => {
    const present = new Set(allRows.map((r) => r.theme));
    return THEME_ORDER.filter((t) => present.has(t));
  }, [allRows]);

  const columns: Column<ConvictionEntry>[] = [
    { key: "rank", label: "#", align: "left", cls: "w-10", value: (r) => r.rank, render: (r) => <span className="font-mono text-text-faint">{r.rank}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} title={`Conviction ${r.grade} — score ${r.score}/100 (analyst rating + trend persistence + RS + target upside)`} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => (
      <span className="flex items-center gap-2">
        <span className="font-bold text-text-primary">{r.symbol}</span>
        <span className="text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">{r.theme}</span>
      </span>
    ) },
    { key: "price", label: "Price", align: "right", value: (r) => r.last_price, render: (r) => <span className="font-mono text-text-primary">{money(r.last_price)}</span> },
    { key: "cap", label: "Mkt Cap", align: "right", cls: "hidden lg:table-cell", value: (r) => r.market_cap ?? 0, render: (r) => <span className="font-mono text-text-secondary">{fmtCap(r.market_cap)}</span> },
    { key: "analyst", label: "Analyst", align: "left", value: (r) => -(r.rec_mean ?? 9), render: (r) => <AnalystCell r={r} /> },
    { key: "upside", label: "Target ↑", align: "right", cls: "hidden md:table-cell", value: (r) => r.target_upside_pct ?? -999, render: (r) => (
      r.target_upside_pct == null ? <span className="text-text-faint">—</span>
        : <span className={`font-mono ${r.target_upside_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.target_upside_pct >= 0 ? "+" : ""}{r.target_upside_pct.toFixed(0)}%</span>
    ) },
    { key: "trend", label: "Above 50MA", align: "left", cls: "hidden sm:table-cell", value: (r) => r.pct_days_above_50, render: (r) => <TrendCell r={r} /> },
    { key: "rs", label: "RS vs SPY", align: "right", cls: "hidden lg:table-cell", value: (r) => r.rs_vs_spy, render: (r) => <span className={`font-mono ${r.rs_vs_spy >= 0 ? "text-accent" : "text-text-muted"}`}>{r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span> },
    { key: "ret20", label: "20d", align: "right", cls: "hidden xl:table-cell", value: (r) => r.ret_20d, render: (r) => <span className={`font-mono ${r.ret_20d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{r.ret_20d >= 0 ? "+" : ""}{r.ret_20d.toFixed(1)}%</span> },
    { key: "score", label: "Score", align: "right", cls: "w-14", value: (r) => r.score, render: (r) => <span className="font-mono font-bold text-text-primary">{r.score}</span> },
    { key: "add", label: "", align: "right", cls: "w-10", render: (r) => <AddButton owned={isOwned(r.symbol)} onAdd={() => addToWatchlist(r.symbol)} label={`Add ${r.symbol} to watchlist`} /> },
  ];

  const pill = "text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-3 text-text-muted";
  const mobileRow = (r: ConvictionEntry) => {
    const m = ratingMeta(r.rec_mean);
    return (
      <div className="space-y-1.5">
        {/* Identity + price + add */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <GradeBadge grade={r.grade} />
            <span className="text-[15px] font-bold text-text-primary">{r.symbol}</span>
            <span className="shrink-0 text-[10px] font-semibold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">{r.theme}</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <span className="font-mono text-sm text-text-primary">{money(r.last_price)}</span>
            <AddButton owned={isOwned(r.symbol)} onAdd={() => addToWatchlist(r.symbol)} label={`Add ${r.symbol} to watchlist`} />
          </div>
        </div>
        {/* Headline signal: rating + score */}
        <div className="flex items-center justify-between gap-2">
          <span className={`text-xs font-semibold ${m.cls}`}>
            {m.label}{r.num_analysts != null ? ` · ${r.num_analysts} analysts` : ""}
          </span>
          <span className="font-mono text-[11px] font-bold text-text-secondary">score {r.score}</span>
        </div>
        {/* Supporting stats as spaced pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={`${pill} ${r.ret_20d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
            {r.ret_20d >= 0 ? "↑" : "↓"}{Math.abs(r.ret_20d).toFixed(0)}% 20d
          </span>
          <span className={pill}>{r.pct_days_above_50.toFixed(0)}% &gt;50MA</span>
          <span className={pill}>RS {r.rs_vs_spy >= 0 ? "+" : ""}{r.rs_vs_spy.toFixed(1)}</span>
          {r.target_upside_pct != null && (
            <span className={`${pill} text-bullish-text`}>tgt +{r.target_upside_pct.toFixed(0)}%</span>
          )}
          {r.ma_stacked && <span className={`${pill} text-accent`}>50&gt;200 ↑</span>}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-2">
            <Gem className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Conviction</h1>
              <p className="text-[11px] text-text-muted">
                Mid-cap AI · chips · disruptive names with strong analyst ratings that trend above the 50-day MA.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs">
            {history.data && history.data.runs.length > 0 && (
              <div className="flex items-center gap-1.5">
                <History className="h-3.5 w-3.5 text-text-muted" />
                <select
                  value={runId ?? ""}
                  onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)}
                  className="bg-surface-1 border border-border-subtle rounded px-2 py-1 text-text-secondary"
                >
                  <option value="">Latest run</option>
                  {history.data.runs.map((r) => (
                    <option key={r.id} value={r.id}>
                      {new Date(`${r.captured_at}Z`).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {r.count}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {captured && <span className="text-text-faint">Updated {captured.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>}
            {isPro && (
              <button
                onClick={() => refresh.mutate()}
                disabled={refresh.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
                {refresh.isPending ? "Scanning…" : "Run scan"}
              </button>
            )}
            {isPro && (
              <button
                onClick={() => syncWatchlist.mutate()}
                disabled={syncWatchlist.isPending}
                title="Add the Strong-Buy names from this scan to your watchlist (a 'Conviction' group)"
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-purple-500/15 text-purple-300 hover:bg-purple-500/25 disabled:opacity-50 transition-colors"
              >
                <Plus className={`h-3.5 w-3.5 ${syncWatchlist.isPending ? "animate-pulse" : ""}`} />
                {syncWatchlist.isPending ? "Syncing…" : "Sync Strong-Buy → watchlist"}
              </button>
            )}
          </div>
        </div>

        {/* Theme filter */}
        {themes.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            {["All", ...themes].map((t) => (
              <button
                key={t}
                onClick={() => setTheme(t)}
                className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
                  theme === t
                    ? "bg-accent/15 text-accent border-accent/40"
                    : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-secondary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        )}

        <ScreenerTable<ConvictionEntry>
          rows={rows}
          columns={columns}
          rowKey={(r) => r.symbol}
          onRowClick={(r) => navigate(`/trading?symbol=${encodeURIComponent(r.symbol)}`)}
          defaultSort={{ key: "score", dir: "desc" }}
          mobileRow={mobileRow}
          isLoading={isLoading}
          isError={isError}
          errorText="Couldn't load the conviction screen."
          empty={
            <div className="px-4 py-10 text-center text-sm text-text-muted">
              No conviction picks in the latest run.
              {isPro && " Tap Run scan to refresh — analyst ratings + 50MA trend over the AI/chips/disruptive universe."}
            </div>
          }
        />

        <p className="text-[11px] text-text-faint leading-relaxed">
          <strong>Score (0–100)</strong> blends analyst rating, mean-target upside, how persistently price holds above the 50-day MA, the 50&gt;200 stack, and relative strength vs SPY. Strong analyst rating + above-50MA are required to appear. Research only — not financial advice; verify the live thesis before acting.
        </p>
    </div>
  );
}
