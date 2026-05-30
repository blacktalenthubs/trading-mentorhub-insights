/** Trade Ideas — forward-looking ideas grouped by source.
 *  Tabs: Day Trades (Pine-rule alerts), Swing Trades (daily-bar scanner),
 *  AI Scans (AI Best Setups, the original FocusListPage content).
 *  File kept as FocusListPage.tsx for git history; the export wraps three
 *  tab subviews. Old route /focus-list redirects to /trade-ideas in App.tsx.
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { RefreshCw, Target, History, Sparkles, Crosshair, Activity } from "lucide-react";
import {
  useAlertsToday,
  useLatestFocusList,
  useFocusListHistory,
  useFocusListDetail,
  useRunFocusList,
  type FocusListHistoryItem,
} from "../api/hooks";
import FocusListView from "../components/FocusListView";
import SwingTradesPage from "./SwingTradesPage";
import InPlayView from "../components/InPlayView";
import TierGate from "../components/TierGate";

type IdeasTab = "day" | "swing" | "ai" | "inplay";

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
  { id: "day",   label: "Day Trades",   icon: Crosshair },
  { id: "swing", label: "Swing Trades", icon: Target },
  { id: "ai",    label: "AI Scans",     icon: Sparkles },
  { id: "inplay", label: "In Play",     icon: Activity },
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
      <div className="mx-auto max-w-4xl px-4 py-5 space-y-4">
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
        {tab === "swing" && <SwingTradesPage />}
        {tab === "ai" && <AIScansTab />}
        {tab === "inplay" && (
          <TierGate require="pro" featureName="In-Play Volume Screener">
            <InPlayView />
          </TierGate>
        )}
      </div>
    </div>
  );
}

/* ── Day Trades tab — today's Pine-rule alerts grouped by symbol ── */

function DayTradesTab() {
  const navigate = useNavigate();
  const { data: alerts } = useAlertsToday();

  // BUY alerts only, dedup by symbol (latest one per symbol shows up).
  const bySymbol = new Map<string, typeof alerts extends (infer T)[] | undefined ? T : never>();
  (alerts ?? []).forEach((a) => {
    if (a.direction !== "BUY") return;
    if (a.user_action === "skipped") return;
    const prev = bySymbol.get(a.symbol);
    // Keep the most recent fire per symbol
    if (!prev || a.created_at > prev.created_at) bySymbol.set(a.symbol, a);
  });
  const ideas = [...bySymbol.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));

  if (!alerts) {
    return <div className="text-center text-xs text-text-faint py-12">Loading…</div>;
  }
  if (ideas.length === 0) {
    return (
      <div className="bg-surface-1 border border-border-subtle rounded-xl p-8 text-center">
        <Crosshair className="h-6 w-6 text-text-faint mx-auto mb-3" />
        <p className="text-sm text-text-secondary">No day trade ideas firing right now.</p>
        <p className="text-xs text-text-faint mt-1">When Pine alerts fire on your watchlist, they'll show up here.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-text-faint">
        Pine-rule alerts fired today, deduped to one entry per symbol (latest fire).
        Tap a row to open the chart.
      </p>
      {ideas.map((a) => {
        const time = new Date(a.created_at).toLocaleTimeString("en-US", {
          hour: "2-digit", minute: "2-digit", timeZone: "America/Chicago",
        });
        const ruleLabel = (a.alert_type || "").replace(/^tv_/, "").replace(/_/g, " ");
        return (
          <button
            key={a.id}
            onClick={() => navigate(`/trading?symbol=${encodeURIComponent(a.symbol)}`)}
            className="w-full flex items-center gap-3 bg-surface-1 hover:bg-surface-2 border border-border-subtle rounded-lg px-4 py-2.5 text-left transition-colors"
          >
            <span className="font-mono text-[10px] text-text-faint w-12">{time}</span>
            <span className="font-bold text-sm text-text-primary w-16">{a.symbol}</span>
            <span className="text-[10px] font-bold text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">BUY</span>
            <span className="text-xs text-text-muted flex-1 truncate">{ruleLabel}</span>
            <span className="font-mono text-xs text-text-secondary">${a.price?.toFixed(2)}</span>
            {a.user_action === "took" && (
              <span className="text-[10px] text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">Took</span>
            )}
          </button>
        );
      })}
    </div>
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
          <FocusListView list={viewing} onSelectSymbol={openChart} />
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
