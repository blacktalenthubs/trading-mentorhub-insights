/** Trade Ideas — forward-looking ideas grouped by source.
 *  Tabs: Day Trades (Pine-rule alerts), Swing Trades (daily-bar scanner),
 *  AI Scans (AI Best Setups, the original FocusListPage content).
 *  File kept as FocusListPage.tsx for git history; the export wraps three
 *  tab subviews. Old route /focus-list redirects to /trade-ideas in App.tsx.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  RefreshCw, Target, History, Sparkles, Crosshair, Flame,
  ChevronDown, ChevronUp, ChevronRight, MessageSquare,
} from "lucide-react";
import {
  useAlertsToday,
  useLatestFocusList,
  useFocusListHistory,
  useFocusListDetail,
  useRunFocusList,
  useSocialBuzz,
  useSocialBuzzHistory,
  useRefreshSocialBuzz,
  useSocialBuzzContext,
  type FocusListHistoryItem,
  type SocialBuzzEntry,
} from "../api/hooks";
import SwingScreenerView from "../components/SwingScreenerView";
// InPlayView removed 2026-06-01 — scanner was too static + redundant with
// Swing+AI Scan. Component file kept on disk for git history.
import { useFeatureGate } from "../hooks/useFeatureGate";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";
import { Skeleton, SkeletonRow } from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import type { Alert } from "../types";
import { type FocusRecommendation } from "../api/hooks";

type IdeasTab = "day" | "swing" | "ai" | "social";

function historyLabel(item: FocusListHistoryItem): string {
  const iso = item.generated_at;
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  const when = isNaN(d.getTime())
    ? item.session_date
    : d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
  const win =
    item.market_window === "pre_open"
      ? "Pre-open"
      : item.market_window === "pre_close"
      ? "Pre-close"
      : "Mid-session";
  const tag = item.status === "failed" ? "failed" : `${item.recommendation_count} setups`;
  return `${when} · ${win} · ${tag}`;
}

const IDEAS_TABS: { id: IdeasTab; label: string; icon: typeof Crosshair }[] = [
  { id: "day",    label: "Day Trades",   icon: Crosshair },
  { id: "swing",  label: "Swing Trades", icon: Target },
  { id: "ai",     label: "AI Scans",     icon: Sparkles },
  { id: "social", label: "Social",       icon: Flame },
];

export default function FocusListPage() {
  const [tab, setTab] = useState<IdeasTab>(() => {
    if (typeof window === "undefined") return "day";
    return (localStorage.getItem("ideas_active_tab") as IdeasTab) || "day";
  });
  function pickTab(t: IdeasTab) {
    setTab(t);
    try { localStorage.setItem("ideas_active_tab", t); } catch {}
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 py-5 space-y-4">
        {/* Header + tab bar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Target className="h-5 w-5 text-accent" />
            <div>
              <h1 className="text-lg font-bold text-text-primary">Trade Ideas</h1>
              <p className="text-[11px] text-text-muted">
                Day trade setups, swing scanner output, and AI scans — what to look at this session.
              </p>
            </div>
          </div>
          <div className="flex bg-surface-2 rounded-lg p-0.5">
            {IDEAS_TABS.map((t) => {
              const Icon = t.icon;
              return (
                <button
                  key={t.id}
                  onClick={() => pickTab(t.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    tab === t.id
                      ? "bg-surface-4 text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <Icon className="h-3 w-3" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Swing is no longer hard-locked: free users see the full screener
            with the top-N rows visible and the rest blurred + an upgrade
            CTA (preview, not padlock). Gating lives in ScreenerTable. */}
        {tab === "day" && <DayTradesTab />}
        {tab === "swing" && <SwingScreenerView />}
        {tab === "ai" && <AIScansTab />}
        {tab === "social" && <SocialBuzzTab />}
      </div>
    </div>
  );
}

/* ── Day Trades tab — today's Pine-rule alerts grouped by symbol ── */

const money = (n: number | null | undefined) => (n != null ? `$${n.toFixed(2)}` : "—");

function DayTradesTab() {
  const navigate = useNavigate();
  const { data: alerts } = useAlertsToday();
  const { visibleAlerts } = useFeatureGate();

  const bySymbol = new Map<string, Alert>();
  (alerts ?? []).forEach((a) => {
    if (a.direction !== "BUY") return;
    if (a.user_action === "skipped") return;
    const prev = bySymbol.get(a.symbol);
    if (!prev || a.created_at > prev.created_at) bySymbol.set(a.symbol, a);
  });
  const ideas = [...bySymbol.values()];

  const ruleLabel = (a: Alert) => (a.alert_type || "").replace(/^tv_/, "").replace(/_/g, " ");
  const timeOf = (a: Alert) =>
    new Date(a.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "America/Chicago" });

  const columns: Column<Alert>[] = [
    { key: "time", label: "Time", align: "left", cls: "w-16", value: (a) => a.created_at, render: (a) => <span className="font-mono text-[11px] text-text-faint">{timeOf(a)}</span> },
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (a) => GRADE_RANK[(a.grade || "C").toUpperCase()] ?? 1, render: (a) => <GradeBadge grade={a.grade} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (a) => a.symbol, render: (a) => (
      <span className="flex items-center gap-2"><span className="font-bold text-text-primary">{a.symbol}</span><span className="text-[10px] font-bold text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">BUY</span></span>
    ) },
    { key: "setup", label: "Setup", align: "left", render: (a) => <span className="text-text-muted capitalize">{ruleLabel(a)}</span> },
    { key: "price", label: "Price", align: "right", value: (a) => a.price ?? 0, render: (a) => <span className="font-mono text-text-primary">{money(a.price)}</span> },
    { key: "entry", label: "Entry", align: "right", cls: "hidden lg:table-cell", value: (a) => a.entry ?? 0, render: (a) => <span className="font-mono text-text-secondary">{money(a.entry)}</span> },
    { key: "stop", label: "Stop", align: "right", cls: "hidden lg:table-cell", render: (a) => <span className="font-mono text-bearish-text">{money(a.stop)}</span> },
    { key: "target", label: "Target", align: "right", cls: "hidden lg:table-cell", render: (a) => <span className="font-mono text-bullish-text">{money(a.target_1)}</span> },
    { key: "took", label: "", align: "right", render: (a) => (a.user_action === "took" ? <span className="text-[10px] text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">Took</span> : null) },
  ];

  const mobileRow = (a: Alert) => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><GradeBadge grade={a.grade} /><span className="font-bold text-text-primary">{a.symbol}</span>
          <span className="text-[10px] font-bold text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">BUY</span>
          {a.user_action === "took" && <span className="text-[10px] text-bullish-text">Took</span>}</div>
        <span className="font-mono text-sm text-text-primary">{money(a.price)}</span>
      </div>
      <div className="flex gap-3 mt-1 text-[11px] text-text-muted font-mono">
        <span className="capitalize text-text-faint">{ruleLabel(a)}</span>
        <span>E {money(a.entry)}</span><span>S {money(a.stop)}</span><span>T {money(a.target_1)}</span>
      </div>
    </>
  );

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-text-faint">Pine-rule alerts fired today, one row per symbol (latest fire). Tap a row to open the chart.</p>
      <ScreenerTable
        rows={ideas}
        columns={columns}
        rowKey={(a) => String(a.id)}
        onRowClick={(a) => navigate(`/trading?symbol=${encodeURIComponent(a.symbol)}`)}
        defaultSort={{ key: "time", dir: "desc" }}
        previewRows={visibleAlerts}
        previewLabel="day-trade ideas"
        mobileRow={mobileRow}
        isLoading={!alerts}
        empty={<EmptyState icon={Crosshair} title="No day-trade ideas firing right now" hint="The intraday scanner watches your watchlist for Pine entry alerts. They'll appear here as they fire — usually within the first 90 minutes of the open." primary={{ label: "Edit watchlist", to: "/watchlist" }} secondary={{ label: "Open trading view", to: "/trading" }} />}
      />
    </div>
  );
}

/* ── AI Scans recommendations as a screener table ── */

function RecommendationsTable({ recs, onSelect }: { recs: FocusRecommendation[]; onSelect: (s: string) => void }) {
  const Dir = ({ d }: { d: string }) => (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${d === "LONG" ? "text-bullish-text bg-bullish/10" : "text-bearish-text bg-bearish/10"}`}>{d}</span>
  );
  const Conv = ({ c }: { c: string }) => {
    const cls = c === "HIGH" ? "text-bullish-text bg-bullish/10" : c === "MEDIUM" ? "text-amber-400 bg-amber-400/10" : "text-text-muted bg-surface-3";
    return <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${cls}`}>{c}</span>;
  };
  const convRank = (c: string) => (({ HIGH: 3, MEDIUM: 2, LOW: 1 } as Record<string, number>)[c] ?? 0);

  const columns: Column<FocusRecommendation>[] = [
    { key: "grade", label: "Grade", align: "left", cls: "w-14", value: (r) => GRADE_RANK[(r.grade || "C").toUpperCase()] ?? 1, render: (r) => <GradeBadge grade={r.grade} /> },
    { key: "symbol", label: "Symbol", align: "left", value: (r) => r.symbol, render: (r) => <span className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span><Dir d={r.direction} /></span> },
    { key: "setup", label: "Setup", align: "left", render: (r) => <span className="text-text-muted">{r.setup_type}</span> },
    { key: "why", label: "Reason", align: "left", cls: "hidden xl:table-cell max-w-[280px]", render: (r) => (
      <span className="text-[11px] text-text-secondary leading-snug line-clamp-2" title={r.why_now}>
        {r.why_now || "—"}
      </span>
    ) },
    { key: "horizon", label: "Horizon", align: "left", cls: "hidden lg:table-cell", render: (r) => <span className="text-text-faint text-xs capitalize">{String(r.trade_horizon).replace(/_/g, " ")}</span> },
    { key: "entry", label: "Entry", align: "right", value: (r) => r.entry, render: (r) => <span className="font-mono text-text-primary">{money(r.entry)}</span> },
    { key: "stop", label: "Stop", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bearish-text">{money(r.stop)}</span> },
    { key: "t1", label: "T1", align: "right", cls: "hidden lg:table-cell", render: (r) => <span className="font-mono text-bullish-text">{money(r.t1)}</span> },
    { key: "dist", label: "To Entry", align: "right", cls: "hidden xl:table-cell", value: (r) => r.distance_to_entry_pct, render: (r) => <span className="font-mono text-text-secondary">{r.distance_to_entry_pct?.toFixed(1)}%</span> },
    { key: "conviction", label: "Conviction", align: "left", value: (r) => convRank(r.conviction), render: (r) => <Conv c={r.conviction} /> },
  ];

  const mobileRow = (r: FocusRecommendation) => (
    <>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2"><span className="font-bold text-text-primary">{r.symbol}</span><Dir d={r.direction} /><Conv c={r.conviction} /></div>
        <span className="font-mono text-sm text-text-primary">{money(r.entry)}</span>
      </div>
      <div className="flex gap-3 mt-1 text-[11px] text-text-muted font-mono"><span className="text-text-faint">{r.setup_type}</span><span>S {money(r.stop)}</span><span>T1 {money(r.t1)}</span></div>
      {r.why_now && (
        <p className="mt-1 text-[11px] text-text-secondary leading-snug line-clamp-2">{r.why_now}</p>
      )}
    </>
  );

  return (
    <ScreenerTable
      rows={recs}
      columns={columns}
      rowKey={(r) => r.symbol}
      onRowClick={(r) => onSelect(r.symbol)}
      defaultSort={{ key: "conviction", dir: "desc" }}
      mobileRow={mobileRow}
      empty={<EmptyState title="No setups in this list" hint="The scan ran but didn't surface any qualifying setups. The market may be quiet, or your watchlist may need fresh tickers." primary={{ label: "Run a new scan", to: "/trade-ideas?tab=ai" }} secondary={{ label: "Edit watchlist", to: "/watchlist" }} />}
    />
  );
}

/* ── AI Scans tab — the original AI Best Setups focus-list flow ── */

function AIScansTab() {
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [cadencePrompt, setCadencePrompt] = useState(false);

  const latest = useLatestFocusList();
  const history = useFocusListHistory();
  const detail = useFocusListDetail(selectedId);
  const runMut = useRunFocusList();

  const viewing = selectedId != null ? detail.data : latest.data;
  const loading =
    selectedId != null ? detail.isLoading : latest.isLoading;

  function openChart(symbol: string) {
    navigate(`/trading?symbol=${encodeURIComponent(symbol)}`);
  }

  async function runScan(force = false) {
    try {
      const res = await runMut.mutateAsync({ force });
      if (res.cadence_check) {
        setCadencePrompt(true);
      } else {
        setCadencePrompt(false);
        setSelectedId(null); // jump back to the freshly saved latest list
      }
    } catch {
      /* error toast handled by the hook (429, network, etc.) */
      setCadencePrompt(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-3">
        <button
          onClick={() => runScan(false)}
          disabled={runMut.isPending}
          className="text-xs px-3 py-1.5 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
            <RefreshCw className={`h-3.5 w-3.5 ${runMut.isPending ? "animate-spin" : ""}`} />
            {runMut.isPending ? "Scanning…" : "Run scan"}
          </button>
        </div>

        {/* History selector */}
        {history.data && history.data.items.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <History className="h-3.5 w-3.5 text-text-muted" />
            <select
              value={selectedId ?? ""}
              onChange={(e) =>
                setSelectedId(e.target.value ? Number(e.target.value) : null)
              }
              className="bg-surface-1 border border-border-subtle rounded px-2 py-1 text-text-secondary"
            >
              <option value="">Latest focus list</option>
              {history.data.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {historyLabel(item)}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Content */}
        {loading && (
          <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 space-y-3">
            <Skeleton w="40%" h={16} />
            <SkeletonRow count={6} h={56} />
          </div>
        )}

        {!loading && !viewing && (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center">
            <Sparkles className="h-8 w-8 mx-auto mb-3 text-accent" />
            <h2 className="text-sm font-bold text-text-primary mb-1">
              No focus list yet
            </h2>
            <p className="text-xs text-text-muted mb-4">
              Run your first scan — the AI ranks your watchlist for the best
              day-trade and swing setups, and the result is saved here.
            </p>
            <button
              onClick={() => runScan(false)}
              disabled={runMut.isPending}
              className="text-xs px-4 py-2 rounded-full bg-accent text-white hover:bg-accent/90 disabled:opacity-50 transition-colors"
            >
              {runMut.isPending ? "Scanning…" : "Run your first scan"}
            </button>
          </div>
        )}

        {!loading && viewing && (
          <RecommendationsTable recs={viewing.recommendations ?? []} onSelect={openChart} />
        )}

      {/* Cadence confirmation dialog */}
      {cadencePrompt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border-subtle bg-surface-1 p-5">
            <h3 className="text-sm font-bold text-text-primary mb-2">
              Run another scan?
            </h3>
            <p className="text-xs text-text-muted mb-4">
              {runMut.data?.message ||
                "You've already run the recommended two scans today. Your saved focus lists are still available without spending another AI run."}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setCadencePrompt(false)}
                className="flex-1 text-xs px-3 py-2 rounded-lg bg-surface-2 text-text-secondary hover:bg-surface-3 transition-colors"
              >
                Keep saved list
              </button>
              <button
                onClick={() => runScan(true)}
                disabled={runMut.isPending}
                className="flex-1 text-xs px-3 py-2 rounded-lg bg-accent text-white hover:bg-accent/90 disabled:opacity-50 transition-colors"
              >
                {runMut.isPending ? "Scanning…" : "Run anyway"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Social Buzz tab — Apewisdom-fed top discussed tickers ─────────── */

function SocialBuzzTab() {
  const navigate = useNavigate();
  const [runId, setRunId] = useState<number | null>(null);  // null = latest live run
  const { data, isLoading, error } = useSocialBuzz(runId);
  const history = useSocialBuzzHistory();
  const refresh = useRefreshSocialBuzz();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sort, setSort] = useState<{ key: SocialSortKey; dir: "asc" | "desc" }>({ key: "mentions", dir: "desc" });

  function toggleExpand(symbol: string) {
    setExpanded((cur) => (cur === symbol ? null : symbol));
  }
  function toggleSort(key: SocialSortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" }));
  }

  if (isLoading) {
    // Skeleton mirroring the actual table shape (8 rows) so the layout
    // doesn't jump when data arrives.
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Skeleton w={220} h={14} />
          <Skeleton w={140} h={26} rounded="full" />
        </div>
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 space-y-3">
          <SkeletonRow count={8} h={36} />
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="text-center py-12 text-sm text-bearish-text">
        Failed to load social buzz.
      </div>
    );
  }

  const entries = data?.entries ?? [];
  const sortedEntries = [...entries].sort((a, b) => {
    const av = socialSortVal(a, sort.key);
    const bv = socialSortVal(b, sort.key);
    const dir = sort.dir === "asc" ? 1 : -1;
    if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
    return (av - bv) * dir;
  });
  if (entries.length === 0) {
    return (
      <EmptyState
        icon={Flame}
        title="No social buzz snapshot yet"
        hint="A scheduled job pulls Reddit/Twitter mention growth every hour. The first snapshot lands within ~60 minutes — or you can trigger one now."
        primary={{ label: "Refresh now", onClick: () => refresh.mutate() }}
      />
    );
  }

  const capturedAge = data?.captured_at
    ? Math.max(0, Math.round((Date.now() - new Date(data.captured_at).getTime()) / 60_000))
    : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-faint">
        <span>
          {entries.length} tickers · tap a column to sort · sources: Apewisdom + StockTwits
        </span>
        <div className="flex items-center gap-3">
          {history.data && history.data.runs.length > 1 && (
            <div className="flex items-center gap-1.5">
              <History className="h-3.5 w-3.5 text-text-muted" />
              <select
                value={runId ?? ""}
                onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)}
                className="bg-surface-1 border border-border-subtle rounded px-2 py-1 text-xs text-text-secondary"
              >
                <option value="">Latest run</option>
                {history.data.runs.map((r) => (
                  <option key={r.id} value={r.id}>
                    {new Date(r.captured_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })} · {r.count} tickers
                  </option>
                ))}
              </select>
            </div>
          )}
          <span className={runId ? "" : data?.stale ? "text-warning-text" : ""}>
            {runId ? "saved run" : capturedAge != null ? `Refreshed ${capturedAge}m ago` : "Loading…"}
            {!runId && data?.stale && " · stale"}
          </span>
          <button
            onClick={() => { setRunId(null); refresh.mutate(); }}
            disabled={refresh.isPending}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors"
            title="Pull the latest Apewisdom snapshot now"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refresh.isPending ? "animate-spin" : ""}`} />
            {refresh.isPending ? "Refreshing…" : "Run scan"}
          </button>
        </div>
      </div>

      <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint font-medium border-b border-border-subtle/50 bg-surface-2/30">
          <span className="col-span-1">#</span>
          <SocialTh label="Symbol" k="symbol" sort={sort} onSort={toggleSort} className="col-span-3" />
          <SocialTh label="Mentions" k="mentions" sort={sort} onSort={toggleSort} align="right" className="col-span-2" />
          <SocialTh label="Δ24h" k="growth" sort={sort} onSort={toggleSort} align="right" className="col-span-2" title="Change in mentions vs 24h ago — new attention" />
          <SocialTh label="Sentiment" k="sentiment" sort={sort} onSort={toggleSort} align="center" className="col-span-2" title="StockTwits bull/bear lean from recent tagged posts" />
          <SocialTh label="Grade A" k="confluence" sort={sort} onSort={toggleSort} align="right" className="col-span-2" title="🔥 = this buzz ticker ALSO fired a Grade-A alert in our scanner today" />
        </div>
        {sortedEntries.map((e, i) => (
          <SocialBuzzRow
            key={e.symbol}
            entry={e}
            rank={i + 1}
            expanded={expanded === e.symbol}
            onToggleExpand={() => toggleExpand(e.symbol)}
            onOpenChart={() => navigate(`/trading?symbol=${encodeURIComponent(e.symbol)}`)}
          />
        ))}
      </div>

      {/* Column legend — make every column self-explanatory */}
      <div className="rounded-lg border border-border-subtle/60 bg-surface-1/40 px-4 py-3 text-[11px] text-text-muted space-y-1.5">
        <p className="text-text-secondary font-semibold text-[10px] uppercase tracking-wider">What the columns mean</p>
        <p><span className="text-text-secondary font-medium">Mentions</span> — how many posts referenced the ticker across Reddit / StockTwits in the last 24h. Higher = more talked about.</p>
        <p><span className="text-text-secondary font-medium">Δ24h</span> — change in mentions vs 24h ago. <span className="text-bullish-text">Green +</span> = attention is <em>rising</em> (fresh); <span className="text-bearish-text">red −</span> = <em>cooling</em>. <span className="text-text-faint">“—”</span> = too little prior data to trust.</p>
        <p><span className="text-text-secondary font-medium">Sentiment</span> — StockTwits bull/bear lean of recent tagged posts (<span className="text-bullish-text">▲ bullish</span> / <span className="text-bearish-text">▼ bearish</span> / <span className="text-amber-400">◆ mixed</span>). Hover for the exact bull/bear %.</p>
        <p><span className="text-text-secondary font-medium">Grade A</span> — 🔥 means this ticker <em>also</em> fired an A-grade technical alert in the scanner today (buzz <strong>+</strong> conviction). “—” = no A-grade alert.</p>
        <p className="text-text-faint pt-1">Buzz only — not a buy signal. Use Grade A for conviction; tap a row to see what's being said.</p>
      </div>
    </div>
  );
}

/* ── One row in the Social Buzz table — expandable to show StockTwits context ── */

type SocialSortKey = "symbol" | "mentions" | "growth" | "sentiment" | "confluence";

function socialSortVal(e: SocialBuzzEntry, key: SocialSortKey): number | string {
  switch (key) {
    case "symbol": return e.symbol;
    case "mentions": return e.mentions;
    case "growth": return e.growth_pct ?? -Infinity;
    case "sentiment": return e.sentiment == null ? -1 : (e.bullish_pct ?? 50);  // bullish floats up
    case "confluence": return e.has_grade_a_today ? 1 : 0;
  }
}

function SocialTh({ label, k, sort, onSort, align, className, title }: {
  label: string;
  k: SocialSortKey;
  sort: { key: SocialSortKey; dir: "asc" | "desc" };
  onSort: (k: SocialSortKey) => void;
  align?: "right" | "center";
  className?: string;
  title?: string;
}) {
  const active = sort.key === k;
  const justify = align === "right" ? "justify-end" : align === "center" ? "justify-center" : "";
  return (
    <button
      onClick={() => onSort(k)}
      title={title}
      className={`flex items-center gap-1 select-none hover:text-text-secondary transition-colors ${justify} ${className ?? ""}`}
    >
      {label}
      {active && (sort.dir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
    </button>
  );
}

function SocialBuzzRow({
  entry: e, rank, expanded, onToggleExpand, onOpenChart,
}: {
  entry: SocialBuzzEntry;
  rank: number;
  expanded: boolean;
  onToggleExpand: () => void;
  onOpenChart: () => void;
}) {
  const growth = e.growth_pct;
  const growthCls = growth == null ? "text-text-faint"
    : growth >= 200 ? "text-bullish-text font-bold"
    : growth >= 50 ? "text-bullish-text"
    : growth > 0 ? "text-bullish-text/80"
    : growth < 0 ? "text-bearish-text/80"
    : "text-text-faint";

  return (
    <div className={`border-b border-border-subtle/30 last:border-b-0 ${e.has_grade_a_today ? "bg-bullish/5" : ""}`}>
      {/* Row */}
      <div className="grid grid-cols-12 gap-2 px-4 py-2.5 items-center text-xs hover:bg-surface-3/40 transition-colors">
        <button
          onClick={onToggleExpand}
          className="col-span-1 flex items-center gap-1 text-text-faint hover:text-text-muted"
          title={expanded ? "Hide context" : "Show what's being said"}
        >
          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          <span className="font-mono">{rank}</span>
        </button>
        <button
          onClick={onOpenChart}
          className="col-span-3 text-left"
          title={`Open chart for ${e.symbol}`}
        >
          <span className="font-semibold text-text-primary">{e.symbol}</span>
          {e.name && (
            <span className="block text-[10px] text-text-faint truncate mt-0.5">
              {e.name}
            </span>
          )}
        </button>
        <span className="col-span-2 text-right font-mono text-text-secondary">
          {e.mentions.toLocaleString()}
        </span>
        <span className={`col-span-2 text-right font-mono ${growthCls}`}>
          {growth == null ? "—" : `${growth >= 0 ? "+" : ""}${growth.toFixed(0)}%`}
        </span>
        <span className="col-span-2 flex justify-center">
          {e.sentiment ? (
            <span
              className={`inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                e.sentiment === "bullish" ? "text-bullish-text bg-bullish/10"
                : e.sentiment === "bearish" ? "text-bearish-text bg-bearish/10"
                : "text-amber-400 bg-amber-400/10"
              }`}
              title={`StockTwits: ${e.bullish_pct ?? 0}% bullish / ${e.bearish_pct ?? 0}% bearish`}
            >
              {e.sentiment === "bullish" ? "▲" : e.sentiment === "bearish" ? "▼" : "◆"} {e.sentiment}
            </span>
          ) : (
            <span className="text-[10px] text-text-faint">—</span>
          )}
        </span>
        <span className="col-span-2 text-right">
          {e.has_grade_a_today ? (
            <span
              className="inline-flex items-center gap-1 text-[10px] font-bold text-bullish-text bg-bullish/15 px-1.5 py-0.5 rounded"
              title="Also fired a Grade A alert in our scanner today"
            >
              🔥 Grade A
            </span>
          ) : (
            <span className="text-[10px] text-text-faint">—</span>
          )}
        </span>
      </div>

      {/* Expanded context panel — lazy-loaded only when row is expanded */}
      {expanded && <SocialContextPanel symbol={e.symbol} />}
    </div>
  );
}

function SocialContextPanel({ symbol }: { symbol: string }) {
  const { data, isLoading, error } = useSocialBuzzContext(symbol);

  if (isLoading) {
    return (
      <div className="px-4 py-3 bg-surface-2/30 border-t border-border-subtle/20 space-y-2">
        <Skeleton w="50%" h={11} />
        <SkeletonRow count={5} h={28} gap={6} />
      </div>
    );
  }

  if (error || data?.error === "fetch_failed") {
    return (
      <div className="px-6 py-4 bg-surface-2/30 border-t border-border-subtle/20 text-[11px] text-bearish-text">
        Couldn't fetch StockTwits stream for {symbol}.
      </div>
    );
  }

  if (data?.error === "not_supported") {
    return (
      <div className="px-6 py-4 bg-surface-2/30 border-t border-border-subtle/20 text-[11px] text-text-faint">
        StockTwits doesn't cover this symbol (typical for crypto + some small caps).
      </div>
    );
  }

  if (!data || data.messages.length === 0) {
    return (
      <div className="px-6 py-4 bg-surface-2/30 border-t border-border-subtle/20 text-[11px] text-text-faint">
        No recent StockTwits messages for {symbol}.
      </div>
    );
  }

  return (
    <div className="px-4 py-3 bg-surface-2/30 border-t border-border-subtle/20 space-y-2">
      {/* Sentiment summary header */}
      <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-text-faint">
        <MessageSquare className="h-3 w-3" />
        <span>Last {data.total_count} posts</span>
        <span>·</span>
        <span className="text-bullish-text font-semibold">{data.bullish_pct.toFixed(0)}% bullish</span>
        <span>·</span>
        <span className="text-bearish-text font-semibold">{data.bearish_pct.toFixed(0)}% bearish</span>
        <span>·</span>
        <span className="text-text-muted">{data.neutral_pct.toFixed(0)}% neutral</span>
      </div>

      {/* Message list */}
      <div className="space-y-1.5">
        {data.messages.map((m) => {
          const dot = m.sentiment === "bullish" ? "🟢"
            : m.sentiment === "bearish" ? "🔴"
            : "⚪";
          const ageStr = m.age_min < 60
            ? `${m.age_min}m`
            : m.age_min < 1440
            ? `${Math.round(m.age_min / 60)}h`
            : `${Math.round(m.age_min / 1440)}d`;
          return (
            <div
              key={m.id}
              className="flex items-start gap-2 text-[11px] py-1 px-2 rounded hover:bg-surface-3/30"
            >
              <span className="text-[10px] shrink-0 leading-snug mt-0.5">{dot}</span>
              <div className="flex-1 min-w-0">
                <div className="text-text-secondary leading-snug line-clamp-2">
                  {m.body}
                </div>
                <div className="text-[10px] text-text-faint mt-0.5">
                  @{m.user}{m.user_followers > 1000 ? ` · ${(m.user_followers / 1000).toFixed(0)}k followers` : ""} · {ageStr} ago
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-text-faint pt-1">
        Source: StockTwits live stream · cached 5 min server-side
      </p>
    </div>
  );
}
