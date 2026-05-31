/** Trade Ideas — forward-looking ideas grouped by source.
 *  Tabs: Day Trades (Pine-rule alerts), Swing Trades (daily-bar scanner),
 *  AI Scans (AI Best Setups, the original FocusListPage content).
 *  File kept as FocusListPage.tsx for git history; the export wraps three
 *  tab subviews. Old route /focus-list redirects to /trade-ideas in App.tsx.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Target, History, Sparkles, Crosshair, Activity, Flame } from "lucide-react";
import {
  useAlertsToday,
  useLatestFocusList,
  useFocusListHistory,
  useFocusListDetail,
  useRunFocusList,
  useSocialBuzz,
  useRefreshSocialBuzz,
  type FocusListHistoryItem,
} from "../api/hooks";
import SwingScreenerView from "../components/SwingScreenerView";
import InPlayView from "../components/InPlayView";
import TierGate from "../components/TierGate";
import ScreenerTable, { type Column } from "../components/ScreenerTable";
import GradeBadge, { GRADE_RANK } from "../components/GradeBadge";
import type { Alert } from "../types";
import { type FocusRecommendation } from "../api/hooks";

type IdeasTab = "day" | "swing" | "ai" | "inplay" | "social";

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
  { id: "inplay", label: "In Play",      icon: Activity },
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

        {tab === "day" && <DayTradesTab />}
        {tab === "swing" && (
          <TierGate require="pro" featureName="Swing Screener">
            <SwingScreenerView />
          </TierGate>
        )}
        {tab === "ai" && <AIScansTab />}
        {tab === "inplay" && (
          <TierGate require="pro" featureName="In-Play Volume Screener">
            <InPlayView />
          </TierGate>
        )}
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
        mobileRow={mobileRow}
        isLoading={!alerts}
        empty={<div className="py-12 text-center"><Crosshair className="h-6 w-6 text-text-faint mx-auto mb-3" /><p className="text-sm text-text-secondary">No day trade ideas firing right now.</p><p className="text-xs text-text-faint mt-1">When Pine alerts fire on your watchlist, they'll show up here.</p></div>}
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
      empty={<div className="py-12 text-center text-sm text-text-muted">No setups in this list.</div>}
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
          <div className="text-center py-16 text-xs text-text-muted">
            <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2 text-accent" />
            Loading focus list…
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
  const { data, isLoading, error } = useSocialBuzz();
  const refresh = useRefreshSocialBuzz();

  if (isLoading) {
    return (
      <div className="text-center py-12 text-sm text-text-faint">
        Loading social buzz…
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
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <Flame className="h-10 w-10 text-text-faint" />
        <p className="text-text-muted">No social buzz snapshot yet</p>
        <p className="text-sm text-text-faint">
          The hourly job populates this tab. First snapshot appears within an hour of deploy.
        </p>
      </div>
    );
  }

  const capturedAge = data?.captured_at
    ? Math.max(0, Math.round((Date.now() - new Date(data.captured_at).getTime()) / 60_000))
    : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-faint">
        <span>
          {entries.length} tickers · sorted by 24h mention growth · source: Apewisdom
        </span>
        <div className="flex items-center gap-3">
          <span className={data?.stale ? "text-warning-text" : ""}>
            {capturedAge != null ? `Refreshed ${capturedAge}m ago` : "Loading…"}
            {data?.stale && " · stale"}
          </span>
          <button
            onClick={() => refresh.mutate()}
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
          <span className="col-span-3">Symbol</span>
          <span className="col-span-2 text-right">Mentions</span>
          <span className="col-span-2 text-right">Δ24h</span>
          <span className="col-span-2 text-center">Sentiment</span>
          <span className="col-span-2 text-right">Confluence</span>
        </div>
        {entries.map((e, i) => {
          const growth = e.growth_pct;
          const growthCls = growth == null ? "text-text-faint"
            : growth >= 200 ? "text-bullish-text font-bold"
            : growth >= 50 ? "text-bullish-text"
            : growth > 0 ? "text-text-secondary"
            : "text-text-faint";

          const sentLabel = e.sentiment == null ? "—"
            : e.sentiment > 0.2 ? "bullish"
            : e.sentiment < -0.2 ? "bearish"
            : "mixed";
          const sentCls = e.sentiment == null ? "text-text-faint"
            : e.sentiment > 0.2 ? "text-bullish-text"
            : e.sentiment < -0.2 ? "text-bearish-text"
            : "text-text-muted";

          return (
            <button
              key={e.symbol}
              onClick={() => navigate(`/trading?symbol=${encodeURIComponent(e.symbol)}`)}
              className={`w-full grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-border-subtle/30 last:border-b-0 items-center text-xs text-left hover:bg-surface-3/40 transition-colors ${
                e.has_grade_a_today ? "bg-bullish/5" : ""
              }`}
            >
              <span className="col-span-1 text-text-faint font-mono">{i + 1}</span>
              <span className="col-span-3">
                <span className="font-semibold text-text-primary">{e.symbol}</span>
                {e.name && (
                  <span className="block text-[10px] text-text-faint truncate mt-0.5">
                    {e.name}
                  </span>
                )}
              </span>
              <span className="col-span-2 text-right font-mono text-text-secondary">
                {e.mentions.toLocaleString()}
              </span>
              <span className={`col-span-2 text-right font-mono ${growthCls}`}>
                {growth == null ? "—" : `${growth >= 0 ? "+" : ""}${growth.toFixed(0)}%`}
              </span>
              <span className={`col-span-2 text-center text-[11px] ${sentCls}`}>
                {sentLabel}
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
            </button>
          );
        })}
      </div>

      <p className="text-[10px] text-text-faint text-center">
        Buzz only — not a buy signal. Cross-reference with the Grade column for conviction.
      </p>
    </div>
  );
}
