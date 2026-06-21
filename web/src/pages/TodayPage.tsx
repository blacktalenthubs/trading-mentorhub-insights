/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  Two tabs:
 *   • Signals  — the quick entry/exit feed (unchanged).
 *   • Briefing — the AI agent's READ on each alert (the narrative that goes to
 *     Telegram), now surfaced in the app, collapsible per alert. The default
 *     place busy users come to see the "why", not just the numbers.
 *  Its own scroll root (AppLayout <main> is overflow-hidden — see
 *  feedback_page_scroll_container).
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, TrendingUp, ChevronRight, ChevronDown, Bot } from "lucide-react";
import { useAlertsToday, useSpyLiveRegime, useBtcLiveRegime, useWatchlistRank } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";
import type { Alert } from "../types";
import { isFeedSignal } from "../lib/alertFormat";
import AlertCard from "../components/AlertCard";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function setupName(a: Alert): string {
  return a.description || a.alert_type.replace(/^tv_/, "").replace(/_/g, " ");
}

function hhmm(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

function RegimeChip({ label, r }: { label: string; r?: SpyRegimeSnapshot }) {
  const ok = r?.status === "ok";
  const weak = !!r?.below_pdl;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] ${!ok ? "bg-surface-3 text-text-faint" : weak ? "bg-bearish-subtle text-bearish-text" : "bg-bullish-subtle text-bullish-text"}`}>
      ● {label} {ok ? (weak ? "WEAK" : "HEALTHY") : "—"}
    </span>
  );
}

function SectionLabel({ children, action, onAction }: { children: ReactNode; action?: string; onAction?: () => void }) {
  return (
    <div className="flex items-center justify-between px-1 mb-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{children}</span>
      {action && <button onClick={onAction} className="inline-flex items-center gap-0.5 text-[11px] text-accent hover:text-accent-hover active:opacity-70">{action}<ChevronRight size={12} /></button>}
    </div>
  );
}

/* ── One Next-Entries / Leaders row + a hover context popover (price, level, RSI, read). ── */
function RankRow({ w, onChart, leader }: { w: import("../types").WatchlistRankItem; onChart: (s: string) => void; leader?: boolean }) {
  return (
    <div className="group relative">
      <button onClick={() => onChart(w.symbol)}
        className="flex w-full items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5 text-left hover:bg-surface-2 active:opacity-80">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <TrendingUp size={13} className={leader ? "text-warning-text" : w.score >= 60 ? "text-bullish-text" : "text-text-muted"} />
            <span className="font-display text-[13px] font-semibold text-text-primary">{w.symbol}</span>
          </div>
          <p className="truncate text-[11.5px] text-text-muted mt-0.5">{w.signal || w.nearest_level || "—"}</p>
        </div>
        <span className={`font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded tabular-nums ${leader ? "bg-warning-subtle text-warning-text" : w.score >= 60 ? "bg-bullish-subtle text-bullish-text" : "bg-surface-3 text-text-faint"}`}>
          {leader ? `RSI ${Math.round(w.rsi ?? 0)}` : Math.round(w.score)}
        </span>
        <ChevronRight size={14} className="text-text-faint" />
      </button>
      <div className="pointer-events-none absolute inset-x-0 top-full z-20 mt-1 hidden rounded-lg border border-border-subtle bg-surface-3 p-2.5 text-[11px] shadow-lg group-hover:block">
        <div className="flex items-baseline justify-between font-semibold text-text-primary">
          <span>{w.symbol}</span><span className="font-mono text-text-secondary">${w.price}</span>
        </div>
        <div className="mt-1 text-text-secondary">{w.nearest_level}</div>
        <div className="mt-0.5 text-text-muted">RSI {w.rsi ?? "—"} · trend {w.factors?.trend ?? 0}/40</div>
        <div className="mt-1 text-text-muted">{w.signal}</div>
      </div>
    </div>
  );
}

/* ── Briefing: one alert's agent read, collapsible. Header = identity; body = narrative. ── */
function BriefingItem({ a, onChart }: { a: Alert; onChart: (s: string) => void }) {
  const [open, setOpen] = useState(false);
  const dir = (a.direction || "").toUpperCase();
  const isLong = dir === "BUY" || dir === "LONG";
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-2.5 p-3 text-left transition-colors hover:bg-surface-2/50"
      >
        <ChevronDown size={15} className={`mt-0.5 shrink-0 text-text-faint transition-transform ${open ? "" : "-rotate-90"}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-display text-[13px] font-bold text-text-primary">{a.symbol}</span>
            <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isLong ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{dir}</span>
            {a.grade && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary">{a.grade}</span>}
            <span className="text-[11px] text-text-faint ml-auto">{hhmm(a.created_at)}</span>
          </div>
          <p className="mt-0.5 text-[12px] capitalize text-text-muted">{setupName(a)}</p>
          {!open && a.narrative && (
            <p className="mt-1 text-[12px] leading-snug text-text-secondary line-clamp-2">{a.narrative}</p>
          )}
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 -mt-1 ml-[26px]">
          <p className="text-[12.5px] leading-relaxed text-text-secondary whitespace-pre-line">{a.narrative}</p>
          <button onClick={() => onChart(a.symbol)} className="mt-2 inline-flex items-center gap-0.5 text-[11px] text-accent hover:text-accent-hover">
            Open chart <ChevronRight size={12} />
          </button>
        </div>
      )}
    </div>
  );
}

export default function TodayPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<"signals" | "briefing">(() => {
    if (typeof window === "undefined") return "signals";
    return (localStorage.getItem("today_tab") as "signals" | "briefing") || "signals";
  });
  function pickTab(t: "signals" | "briefing") {
    setTab(t);
    try { localStorage.setItem("today_tab", t); } catch { /* ignore */ }
  }

  const { data: alerts } = useAlertsToday();
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  const { data: rank } = useWatchlistRank();

  const goChart = (symbol: string) => nav(`/trading?symbol=${encodeURIComponent(symbol)}`);

  // Live feed = un-acted signals only. Once Took or Declined, an alert leaves the queue.
  const liveSignals = useMemo(
    () => (alerts ?? [])
      .filter((a) => isFeedSignal(a.alert_type) && !a.suppressed_reason && !a.user_action)
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""))
      .slice(0, 12),
    [alerts],
  );
  // Briefing = every alert that carries an agent read, newest first.
  const briefing = useMemo(
    () => (alerts ?? [])
      .filter((a) => a.narrative && a.narrative.trim().length > 0)
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")),
    [alerts],
  );
  const took = useMemo(() => (alerts ?? []).filter((a) => a.user_action === "took"), [alerts]);
  const coiling = useMemo(() => (rank ?? []).filter((r) => r.bucket !== "leader").slice(0, 5), [rank]);
  const leaders = useMemo(() => (rank ?? []).filter((r) => r.bucket === "leader").sort((a, b) => (b.rsi ?? 0) - (a.rsi ?? 0)).slice(0, 5), [rank]);

  const dayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6 pb-16">
        {/* market read + posture */}
        <header className="pb-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="font-display text-lg font-semibold text-text-primary">{greeting()}</h1>
            <div className="flex items-center gap-2">
              <RegimeChip label="SPY" r={spy} />
              <RegimeChip label="BTC" r={btc} />
            </div>
          </div>
          <div className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-text-muted">
            <ShieldCheck size={14} className="text-text-faint" /> Stops on every position ·{" "}
            <span className={spy?.below_pdl ? "text-warning-text font-medium" : "text-bullish-text font-medium"}>
              {spy?.below_pdl ? "DEFENSIVE" : "NORMAL"}
            </span>
          </div>
        </header>

        {/* tabs */}
        <div className="flex items-center gap-1 mb-4 bg-surface-2 rounded-lg p-0.5 w-fit">
          {([["signals", "Signals"], ["briefing", "Briefing"]] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => pickTab(id)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 text-[12px] font-semibold rounded-md transition-colors ${
                tab === id ? "bg-surface-4 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {id === "briefing" && <Bot size={13} />}
              {label}
              {id === "briefing" && briefing.length > 0 && (
                <span className="text-[10px] font-bold text-accent">{briefing.length}</span>
              )}
            </button>
          ))}
        </div>

        {tab === "signals" && (
          <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
            {/* main column — live signals */}
            <section className="lg:col-span-2">
              <SectionLabel action="Trading" onAction={() => nav("/trading")}>Live signals</SectionLabel>
              {liveSignals.length > 0 ? (
                <div className="space-y-2.5">
                  {liveSignals.map((a, i) => <AlertCard key={a.id} a={a} onChart={goChart} defaultExpanded={i < 2} />)}
                </div>
              ) : (
                <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
                  No live signals yet today. The market read above tells you the regime.
                </div>
              )}
            </section>

            {/* side column — worth watching + your day */}
            <div className="space-y-6">
              {coiling.length > 0 && (
                <section>
                  <SectionLabel>Next entries · coiling for a long</SectionLabel>
                  <div className="space-y-1.5">
                    {coiling.map((w) => <RankRow key={w.symbol} w={w} onChart={goChart} />)}
                  </div>
                </section>
              )}
              {leaders.length > 0 && (
                <section>
                  <SectionLabel>Leaders · strong but extended</SectionLabel>
                  <div className="space-y-1.5">
                    {leaders.map((w) => <RankRow key={w.symbol} w={w} onChart={goChart} leader />)}
                  </div>
                </section>
              )}
              <section>
                <SectionLabel>Your day</SectionLabel>
                <div className="rounded-xl border border-border-subtle bg-surface-1 p-3.5">
                  <div className="flex items-center justify-between text-[12px]">
                    <span className="text-text-secondary">
                      {took.length > 0 ? `${took.length} position${took.length > 1 ? "s" : ""} marked Took` : "No positions marked yet"}
                    </span>
                    <button onClick={() => nav("/performance")} className="text-[11px] text-accent hover:text-accent-hover">EOD review →</button>
                  </div>
                  <p className="mt-1.5 text-[11.5px] text-text-faint">At close, review which signals you took — that's how we learn which patterns pay.</p>
                </div>
              </section>
            </div>
          </div>
        )}

        {tab === "briefing" && (
          <div className="max-w-2xl">
            <div className="flex items-center gap-2 px-1 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{dayLabel}</span>
              <span className="text-[11px] text-text-faint">· the AI read on each alert (also sent to Telegram)</span>
            </div>
            {briefing.length > 0 ? (
              <div className="space-y-2">
                {briefing.map((a) => <BriefingItem key={a.id} a={a} onChart={goChart} />)}
              </div>
            ) : (
              <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
                No agent notes yet today. When an alert fires, its AI read appears here — the same write-up that goes to Telegram.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
