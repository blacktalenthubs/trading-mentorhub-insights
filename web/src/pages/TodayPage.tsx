/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  Two tabs:
 *   • Signals  — the quick entry/exit feed (unchanged).
 *   • Briefing — the AI agent's READ on each alert (the narrative that goes to
 *     Telegram), now surfaced in the app, collapsible per alert. The default
 *     place busy users come to see the "why", not just the numbers.
 *  Its own scroll root (AppLayout <main> is overflow-hidden — see
 *  feedback_page_scroll_container).
 */
import { useMemo, useState, useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, TrendingUp, TrendingDown, ChevronRight, ChevronDown, Bot } from "lucide-react";
import { useAlertsToday, useSpyLiveRegime, useBtcLiveRegime, useWatchlistRank, useScanner, useMarketReports, useReportDates, useBottomWatch, type BottomWatchItem } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";
import type { Alert, SignalResult } from "../types";
import { isFeedSignal } from "../lib/alertFormat";
import AlertCard from "../components/AlertCard";
import MasterAlertsBanner from "../components/MasterAlertsBanner";

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

/* ── Trade-idea badge + row — conviction / long-term names the scanner folded into
   Today because they're at (or approaching) entry. Mirrors the Trading-tab badge:
   SOLID at entry, OUTLINE when only approaching; conviction = accent, long-term = green. ── */
function IdeaBadge({ source, actionLabel }: { source?: string; actionLabel?: string }) {
  if (!source || source === "watchlist") return null;
  const atEntry = actionLabel === "Potential Entry";
  const isConv = source === "conviction";
  const tone = isConv
    ? (atEntry ? "bg-accent/15 text-accent border-transparent" : "text-accent border-accent/40")
    : (atEntry ? "bg-bullish/15 text-bullish-text border-transparent" : "text-bullish-text border-bullish/40");
  return (
    <span
      className={`shrink-0 inline-flex items-center text-[9px] font-bold uppercase tracking-wide px-1 py-px rounded border leading-none ${tone}`}
      title={`${isConv ? "Conviction" : "Long-term (swing)"} idea — ${atEntry ? "at entry today" : "approaching entry"}`}
    >
      {isConv ? "Conv" : "LT"}
    </span>
  );
}

function ideaFmt(n: number | null): string {
  if (n == null) return "—";
  return n >= 1000 ? n.toLocaleString(undefined, { maximumFractionDigits: 0 }) : n.toFixed(2);
}

/* The entry is the support level the name is pulling back to: AT SUPPORT = buy
   zone now, PULLBACK WATCH = approaching it. Spells out WHERE the Entry price
   comes from so a user isn't trusting a bare number. */
function whyIdea(s: SignalResult): string {
  const lvl = s.support_label || "support";
  if (s.action_label === "Potential Entry") return `At ${lvl} — buy zone`;
  const dist = s.distance_pct != null ? ` · ${Math.abs(s.distance_pct).toFixed(1)}% away` : "";
  return `Pulling back to ${lvl}${dist}`;
}

function IdeaRow({ s, onChart }: { s: SignalResult; onChart: (sym: string) => void }) {
  const atEntry = s.action_label === "Potential Entry";
  return (
    <button
      onClick={() => onChart(s.symbol)}
      className="w-full text-left rounded-xl border border-border-subtle bg-surface-1 p-3 hover:bg-surface-2/40 transition-colors"
      title={`Entry = ${s.support_label || "support"} (${atEntry ? "price is at the level — buy zone" : "price approaching the level"}). Target = next level up; stop just below the level.`}
    >
      <div className="flex items-center gap-2">
        <span className="font-display font-semibold text-text-primary">{s.symbol}</span>
        <IdeaBadge source={s.source} actionLabel={s.action_label} />
        <span className={`text-[10px] font-medium ${atEntry ? "text-bullish-text" : "text-text-faint"}`}>{atEntry ? "at entry" : "approaching"}</span>
        <ChevronRight size={14} className="ml-auto shrink-0 text-text-faint" />
      </div>
      <p className={`mt-1 text-[12px] leading-snug ${atEntry ? "text-text-secondary" : "text-text-muted"}`}>{whyIdea(s)}</p>
      {(s.entry != null || s.target_1 != null || s.stop != null) && (
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[11px] tabular-nums text-text-muted">
          {s.entry != null && <span>Entry <span className="text-text-secondary">{ideaFmt(s.entry)}</span></span>}
          {s.target_1 != null && <span className="text-bullish-text">Target {ideaFmt(s.target_1)}</span>}
          {s.stop != null && <span>Stop <span className="text-bearish-text">{ideaFmt(s.stop)}</span></span>}
        </div>
      )}
    </button>
  );
}

/* ── One Next-Entries / Leaders row + a hover context popover (price, level, RSI, read). ── */
function RankRow({ w, onChart, leader, losing }: { w: import("../types").WatchlistRankItem; onChart: (s: string) => void; leader?: boolean; losing?: boolean }) {
  const iconCls = losing ? "text-bearish-text rotate-180" : leader ? "text-warning-text" : w.score >= 60 ? "text-bullish-text" : "text-text-muted";
  const badgeCls = losing ? "bg-bearish-subtle text-bearish-text" : leader ? "bg-warning-subtle text-warning-text" : w.score >= 60 ? "bg-bullish-subtle text-bullish-text" : "bg-surface-3 text-text-faint";
  return (
    <div className="group relative">
      <button onClick={() => onChart(w.symbol)}
        className="flex w-full items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5 text-left hover:bg-surface-2 active:opacity-80">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <TrendingUp size={13} className={iconCls} />
            <span className="font-display text-[13px] font-semibold text-text-primary">{w.symbol}</span>
            <span className="font-mono text-[10.5px] text-text-faint">${w.price}</span>
          </div>
          <p className="line-clamp-2 text-[11.5px] text-text-muted mt-0.5">{w.signal || w.nearest_level || "—"}</p>
        </div>
        <span className={`font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded tabular-nums ${badgeCls}`}>
          {leader || losing ? `RSI ${Math.round(w.rsi ?? 0)}` : Math.round(w.score)}
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

/* ── DayRead: the always-on "your day in 30 seconds", synthesized from the page data
   (regime + signals + coiling + leaders) — no AI call, instant, useful even with 0 signals. ── */
function Stat({ n, label, tone, target, onJump }: { n: number; label: string; tone?: "bull" | "warn" | "bear"; target?: string; onJump?: (t: string) => void }) {
  const c = tone === "bull" ? "text-bullish-text" : tone === "warn" ? "text-warning-text" : tone === "bear" ? "text-bearish-text" : "text-text-secondary";
  const go = () => { if (target && onJump) onJump(target); };
  return (
    <button type="button" onClick={go} disabled={!target || n === 0}
      className="rounded-lg bg-surface-2 px-2 py-2 text-center transition-colors enabled:hover:bg-surface-3 enabled:active:opacity-80 disabled:cursor-default">
      <div className={`font-mono text-[17px] font-bold leading-none ${n > 0 ? c : "text-text-faint"}`}>{n}</div>
      <div className="mt-1 text-[9.5px] uppercase tracking-wide text-text-faint">{label}</div>
    </button>
  );
}

function DayRead({ spy, btc, signals, ideas, coiling, leaders, losing, onJump }: {
  spy?: SpyRegimeSnapshot;
  btc?: SpyRegimeSnapshot;
  signals: number;
  ideas: number;
  coiling: import("../types").WatchlistRankItem[];
  leaders: import("../types").WatchlistRankItem[];
  losing: import("../types").WatchlistRankItem[];
  onJump: (t: string) => void;
}) {
  const healthy = !!spy && !spy.below_pdl;
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-4 mb-3">
      <div className="flex items-center gap-2 mb-2.5">
        <Bot size={15} className="text-accent" />
        <span className="font-display text-[13px] font-semibold text-text-primary">Your day in 30 seconds</span>
        <span className={`ml-auto text-[10.5px] font-semibold px-2 py-0.5 rounded-full ${healthy ? "bg-bullish-subtle text-bullish-text" : "bg-warning-subtle text-warning-text"}`}>
          {healthy ? "HEALTHY" : "DEFENSIVE"}
        </span>
      </div>
      <p className="text-[12.5px] leading-relaxed text-text-secondary mb-3">
        SPY {spy?.below_pdl ? "lost" : "holding"} its prior-day low{btc ? `, BTC ${btc.below_pdl ? "weak" : "healthy"}` : ""}.{" "}
        {healthy ? "Long setups in play — long-biased, stops on every position." : "Tighten up — favor cash / proven names, stops on every position."}
      </p>
      <div className="grid grid-cols-5 gap-2">
        <Stat n={signals} label="Fired" />
        <Stat n={ideas} label="Ideas" tone="bull" target="rail-ideas" onJump={onJump} />
        <Stat n={coiling.length} label="Coiling" tone="bull" target="rail-coiling" onJump={onJump} />
        <Stat n={leaders.length} label="Leaders" tone="warn" target="rail-leaders" onJump={onJump} />
        <Stat n={losing.length} label="Breaking" tone="bear" target="rail-losing" onJump={onJump} />
      </div>
    </div>
  );
}

/* ── Market reports: the SAME daily intelligence sent to Telegram — the morning
   Premarket Heat brief (premarket.py) and the EOD Recap (eod.py), persisted by
   triage-agent. Premarket/EOD toggle defaults to whichever dropped most recently. ── */
type SwingPick = {
  symbol: string; pattern?: string; type: string; price: number; buy_point: number;
  buy_range: [number, number]; position: string; stop: number; state?: string; reasons: string[];
};
type DayPick = {
  symbol: string; setup: string; type: string; price: number; entry: number; level: number;
  stop: number; target?: number | null; rsi?: number; position: string; reasons: string[];
};

function ReasonList({ reasons }: { reasons: string[] }) {
  return (
    <ul className="space-y-0.5">
      {reasons.map((r, i) => (
        <li key={i} className="flex gap-1.5 text-[12px] text-text-secondary">
          <span className="text-accent">•</span><span>{r}</span>
        </li>
      ))}
    </ul>
  );
}

function SwingCard({ p, onChart }: { p: SwingPick; onChart: (s: string) => void }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 shadow-card overflow-hidden">
      <button onClick={() => onChart(p.symbol)} className="flex w-full items-center gap-2 px-3.5 py-3 text-left transition-colors hover:bg-surface-2/40">
        <span className="font-display text-[15px] font-bold text-text-primary">{p.symbol}</span>
        {p.pattern && <span className="rounded border border-bullish-muted bg-bullish-subtle px-1.5 py-0.5 text-[10px] font-bold text-bullish-text">{p.pattern}</span>}
        <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-bold text-text-secondary">{p.position} size</span>
        <span className="ml-auto text-[11px] font-semibold text-accent">Analyze →</span>
      </button>
      <div className="space-y-2 px-3.5 pb-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] tabular-nums">
          <span className="font-semibold text-bullish-text">Buy ${p.buy_point.toFixed(2)}</span>
          <span className="text-text-muted">range ${p.buy_range[0].toFixed(2)}–${p.buy_range[1].toFixed(2)}</span>
          <span className="text-bearish-text">Stop ${p.stop.toFixed(2)}</span>
        </div>
        <ReasonList reasons={p.reasons} />
      </div>
    </div>
  );
}

function DayCard({ p, onChart }: { p: DayPick; onChart: (s: string) => void }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 shadow-card overflow-hidden">
      <button onClick={() => onChart(p.symbol)} className="flex w-full items-center gap-2 px-3.5 py-3 text-left transition-colors hover:bg-surface-2/40">
        <span className="font-display text-[15px] font-bold text-text-primary">{p.symbol}</span>
        <span className="rounded border border-bullish-muted bg-bullish-subtle px-1.5 py-0.5 text-[10px] font-bold text-bullish-text">{p.setup}</span>
        <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-bold text-text-secondary">{p.position} size</span>
        {p.rsi != null && <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-semibold text-text-muted">RSI {p.rsi}</span>}
        <span className="ml-auto text-[11px] font-semibold text-accent">Analyze →</span>
      </button>
      <div className="space-y-2 px-3.5 pb-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] tabular-nums">
          <span className="font-semibold text-bullish-text">Entry ${p.entry.toFixed(2)}</span>
          <span className="text-bearish-text">Stop ${p.stop.toFixed(2)}</span>
          {p.target != null && <span className="text-text-muted">Target ${p.target.toFixed(2)}</span>}
        </div>
        <ReasonList reasons={p.reasons} />
      </div>
    </div>
  );
}

/* Today's Focus — two sections: SWING (monthly MoBO + RC-H breakouts) and DAY-TRADE
   (liquid mega-caps defending a key level / oversold / near a breakout). Symbol is
   clickable → Trading chart. Falls back to plain text for old (non-JSON) reports;
   reads the legacy `picks` as swing for reports persisted before the two-section split. */
function FocusPicks({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: { market_ok?: boolean; swing?: SwingPick[]; daytrade?: DayPick[]; picks?: SwingPick[] } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  if (!parsed || (!parsed.swing && !parsed.daytrade && !parsed.picks)) {
    return (
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
        <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-text-secondary">{body.replace(/<\/?(pre|b|i|code|strong|em)>/gi, "")}</pre>
      </div>
    );
  }
  const market_ok = parsed.market_ok;
  const swing = parsed.swing ?? parsed.picks ?? [];
  const daytrade = parsed.daytrade ?? [];
  return (
    <div className="space-y-4">
      <div className={`text-[12px] font-semibold ${market_ok ? "text-bullish-text" : "text-bearish-text"}`}>
        {market_ok ? "🟢 Market healthy — can size up" : "🔴 Market weak — be selective (half size)"}
      </div>
      <section className="space-y-2.5">
        <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Swing · monthly breakout</h3>
        {swing.length === 0 ? (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">
            No name is at a monthly breakout today — nothing to chase. Patience.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            {swing.map((p) => <SwingCard key={p.symbol} p={p} onChart={onChart} />)}
          </div>
        )}
      </section>
      <section className="space-y-2.5">
        <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Today's Focus · the turn · the hold · the breakout</h3>
        {daytrade.length === 0 ? (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">
            No liquid leader is at a key level today.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            {daytrade.map((p) => <DayCard key={p.symbol} p={p} onChart={onChart} />)}
          </div>
        )}
      </section>
    </div>
  );
}

type TrendRow = { symbol: string; price: number; ema20: number; ema50: number; adx: number; dist_pct: number; stop: number };
function TrendSetups({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: { ready_now?: TrendRow[]; extended?: TrendRow[]; rolling_off?: TrendRow[] } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  if (!parsed || (!parsed.ready_now && !parsed.extended)) {
    return (
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
        <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-text-secondary">{body.replace(/<\/?(pre|b|i|code|strong|em)>/gi, "")}</pre>
      </div>
    );
  }
  const ready = parsed.ready_now ?? [];
  const extended = parsed.extended ?? [];
  const rolling = parsed.rolling_off ?? [];
  return (
    <div className="space-y-4">
      <section className="space-y-2.5">
        <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Ready now · at a rising 20 EMA — enter the line</h3>
        {ready.length === 0 ? (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">
            No name is at its 20 EMA today — wait for a pullback to the line.
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            {ready.map((r) => (
              <button key={r.symbol} onClick={() => onChart(r.symbol)} className="text-left rounded-xl border border-accent/40 bg-accent/5 p-3 hover:border-accent transition-colors">
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-bold text-text-secondary">{r.symbol}</span>
                  <span className="text-[10px] font-bold uppercase tracking-wide text-bullish-text">Ready · ADX {r.adx}</span>
                </div>
                <div className="mt-1 text-[12px] text-text-secondary">Entry <b className="text-bullish-text">${r.ema20}</b> (the 20) · stop <b>${r.stop}</b></div>
                <div className="mt-0.5 text-[11px] text-text-faint">now ${r.price} · {r.dist_pct >= 0 ? "+" : ""}{r.dist_pct}% from the 20</div>
              </button>
            ))}
          </div>
        )}
      </section>
      <section className="space-y-2.5">
        <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Extended · strong trend — wait for a pullback to the 20</h3>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
          {extended.map((r) => (
            <button key={r.symbol} onClick={() => onChart(r.symbol)} className="text-left rounded-lg border border-border-subtle bg-surface-1 p-2.5 hover:border-accent transition-colors">
              <div className="flex items-center justify-between">
                <span className="text-[12px] font-bold text-text-secondary">{r.symbol}</span>
                <span className="text-[10px] text-text-faint">ADX {r.adx}</span>
              </div>
              <div className="mt-0.5 text-[11px] text-text-muted">+{r.dist_pct}% above · 20 @ ${r.ema20}</div>
            </button>
          ))}
        </div>
      </section>
      {rolling.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-muted">Rolling off · lost the 20 (not a trend entry)</h3>
          <div className="flex flex-wrap gap-1.5">
            {rolling.map((r) => (
              <button key={r.symbol} onClick={() => onChart(r.symbol)} className="rounded-md bg-surface-2 px-2 py-1 text-[11px] text-text-faint hover:text-text-secondary transition-colors">{r.symbol}</button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function ReportsView({ onChart }: { onChart: (s: string) => void }) {
  // Per-day review — "" = latest; pick a past session to flip back to its reports.
  const [selectedDate, setSelectedDate] = useState("");
  const { data, isLoading } = useMarketReports(selectedDate || undefined);
  const { data: datesData } = useReportDates();
  const reportDates = datesData?.dates ?? [];
  const fmtDate = (d: string) =>
    new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const pre = data?.premarket ?? null;
  const eod = data?.eod ?? null;
  const mf = data?.morning_focus ?? null;
  const ts = data?.trend_setups ?? null;
  type Tab = "focus" | "premarket" | "eod" | "trend";
  // Default to the freshest report by created_at.
  const byTime: Record<Tab, string> = {
    focus: mf?.created_at || "", premarket: pre?.created_at || "", eod: eod?.created_at || "", trend: ts?.created_at || "",
  };
  const freshest = (["focus", "premarket", "eod", "trend"] as Tab[])
    .filter((t) => byTime[t])
    .sort((a, b) => (byTime[a] > byTime[b] ? -1 : 1))[0] || "focus";
  const [which, setWhich] = useState<Tab>(freshest);
  const lastFresh = useRef<string | null>(null);
  useEffect(() => {
    const key = `${byTime.focus}|${byTime.premarket}|${byTime.eod}|${byTime.trend}`;
    if (lastFresh.current !== key && (pre || eod || mf || ts)) {
      lastFresh.current = key;
      setWhich(freshest);
    }
  }, [mf, pre, eod, ts, freshest, byTime.focus, byTime.premarket, byTime.eod, byTime.trend]);

  if (isLoading) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">Loading reports…</div>;
  }
  const active = which === "eod" ? eod : which === "focus" ? mf : which === "trend" ? ts : pre;
  const text = active?.body?.replace(/<\/?(pre|b|i|code|strong|em)>/gi, "");
  const present: Record<Tab, boolean> = { focus: !!mf, premarket: !!pre, eod: !!eod, trend: !!ts };
  const empty: Record<Tab, string> = {
    focus: "No focus picks yet — today's Leaders Near a Buy Point drop pre-open (~8:45 AM ET) and show here.",
    premarket: "No premarket brief yet — it drops pre-open (~8:30 AM ET) and shows here.",
    eod: "No EOD recap yet — it's generated after the close (~4:05 PM ET) and shows here.",
    trend: "No trend setups yet — they're generated after the close (~4:15 PM ET) and show here.",
  };
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        {([["focus", "Today's Focus"], ["trend", "Trend Setups"], ["premarket", "Premarket"], ["eod", "EOD Recap"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setWhich(id)}
            className={`rounded-lg px-3 py-1.5 text-[12px] font-semibold transition-colors ${
              which === id ? "bg-accent/15 text-accent" : "bg-surface-2 text-text-muted hover:text-text-secondary"
            } ${present[id] ? "" : "opacity-50"}`}
          >
            {label}
          </button>
        ))}
        {reportDates.length > 0 && (
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            title="Review a past session"
            className="ml-auto rounded-lg bg-surface-2 border border-border-subtle px-2 py-1.5 text-[11px] text-text-secondary"
          >
            <option value="">Latest</option>
            {reportDates.map((d) => (
              <option key={d} value={d}>{fmtDate(d)}</option>
            ))}
          </select>
        )}
      </div>
      {active?.body ? (
        which === "focus"
          ? <FocusPicks body={active.body} onChart={onChart} />
          : which === "trend"
          ? <TrendSetups body={active.body} onChart={onChart} />
          : (
            <div className="max-w-3xl rounded-xl border border-border-subtle bg-surface-1 p-4">
              <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-text-secondary">{text}</pre>
            </div>
          )
      ) : (
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
          {empty[which]}
        </div>
      )}
    </div>
  );
}

/* ── Signals grouped by symbol: collapsed = one summary row; expand = all its cards. ── */
function SymbolGroup({ symbol, list, onChart, defaultOpen }: { symbol: string; list: Alert[]; onChart: (s: string) => void; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(!!defaultOpen);
  const latest = list[0];
  const best = list.reduce((b, a) => ((a.grade || "Z") < (b.grade || "Z") ? a : b), latest);
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2.5 p-3 text-left transition-colors hover:bg-surface-2/50">
        <ChevronDown size={15} className={`shrink-0 text-text-faint transition-transform ${open ? "" : "-rotate-90"}`} />
        <span className="font-display text-[13px] font-bold text-text-primary">{symbol}</span>
        {list.length > 1 && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-accent/15 text-accent">{list.length}</span>}
        <span className="min-w-0 flex-1 truncate text-[12px] capitalize text-text-muted">{setupName(latest)}</span>
        {best.grade && <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-surface-3 text-text-secondary">{best.grade}</span>}
        <span className="text-[11px] text-text-faint tabular-nums">{hhmm(latest.created_at)}</span>
      </button>
      {open && (
        <div className="border-t border-border-subtle p-2 space-y-2">
          {list.map((a, i) => (
            <div key={a.id} className={a.delivered === false ? "opacity-70" : ""}>
              {a.delivered === false && (
                <div className="mb-1 inline-flex items-center gap-1 rounded bg-surface-3 px-1.5 py-0.5 text-[9px] font-semibold text-text-faint" title={a.suppressed_reason || "not delivered"}>
                  🔕 tracked · not sent{a.suppressed_reason ? ` · ${a.suppressed_reason.replace(/_/g, " ")}` : ""}
                </div>
              )}
              <AlertCard a={a} onChart={onChart} defaultExpanded={i === 0} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Bottom Watch — watchlist ranked by daily RSI. Catch the bottom in washed-out
   names + judge if it's worth buying (P/E, EPS, analyst rating, target upside). ── */
function bwTone(state: BottomWatchItem["state"]): string {
  if (state === "reclaimed_30") return "bg-accent/15 text-accent";
  if (state === "oversold") return "bg-bearish/15 text-bearish-text";
  if (state === "buy_zone") return "bg-warning/15 text-warning-text";
  if (state === "approaching") return "bg-warning/10 text-warning-text";
  if (state === "at_200ma") return "bg-accent/10 text-accent";
  return "bg-surface-3 text-text-muted";
}
const BW_STATE_RANK: Record<BottomWatchItem["state"], number> = {
  reclaimed_30: 0, oversold: 1, buy_zone: 2, approaching: 3, at_200ma: 4, cooling: 5,
};
const BW_REC_RANK: Record<string, number> = {
  strong_buy: 0, buy: 1, hold: 2, underperform: 3, sell: 4,
};
function bwCap(c: number | null | undefined): string {
  if (!c) return "—";
  if (c >= 1e12) return `$${(c / 1e12).toFixed(1)}T`;
  if (c >= 1e9) return `$${(c / 1e9).toFixed(0)}B`;
  return `$${(c / 1e6).toFixed(0)}M`;
}
function bwRec(rec: string | null | undefined): string {
  if (!rec) return "—";
  return rec.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}
type BwSortKey = "symbol" | "rsi" | "state" | "dist" | "pe" | "rec" | "upside" | "cap";
function bwVal(w: BottomWatchItem, k: BwSortKey): number | string | null {
  switch (k) {
    case "symbol": return w.symbol;
    case "rsi": return w.rsi;
    case "state": return BW_STATE_RANK[w.state];
    case "dist": return w.dist_200ma_pct;
    case "pe": return w.fund?.pe ?? null;
    case "rec": return w.fund?.rec ? (BW_REC_RANK[w.fund.rec] ?? 9) : null;
    case "upside": return w.fund?.target_upside_pct ?? null;
    case "cap": return w.fund?.mkt_cap ?? null;
  }
}
function BottomWatchBoard({ onChart }: { onChart: (s: string) => void }) {
  const { data, isLoading } = useBottomWatch();
  const [sortKey, setSortKey] = useState<BwSortKey>("rsi");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const rows = data ?? [];
  const sorted = useMemo(() => {
    const arr = [...rows];
    arr.sort((a, b) => {
      const va = bwVal(a, sortKey), vb = bwVal(b, sortKey);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;       // nulls always sink
      if (vb == null) return -1;
      const c = typeof va === "string" ? va.localeCompare(vb as string) : (va as number) - (vb as number);
      return sortDir === "asc" ? c : -c;
    });
    return arr;
  }, [rows, sortKey, sortDir]);
  const onSort = (k: BwSortKey) => {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setSortDir(k === "symbol" || k === "rsi" ? "asc" : "desc"); }
  };
  const Th = ({ k, label, right }: { k: BwSortKey; label: string; right?: boolean }) => (
    <th className={`px-2.5 py-2 font-medium ${right ? "text-right" : "text-left"}`}>
      <button onClick={() => onSort(k)} className="inline-flex items-center gap-0.5 hover:text-text-secondary">
        {label}{sortKey === k ? (sortDir === "asc" ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );

  if (isLoading && rows.length === 0)
    return <div className="p-8 text-center text-sm text-text-muted">Scanning RSI…</div>;
  if (rows.length === 0)
    return <div className="p-8 text-center text-sm text-text-muted">No names to rank yet.</div>;
  return (
    <div className="space-y-2">
      <p className="px-1 text-[12px] leading-relaxed text-text-muted">
        The market's washed-out names ranked by <b>daily RSI</b> (not just your watchlist) — catch the bottom, then judge if it's worth buying:
        <b> P/E</b> + <b>analyst rating</b> + <b>target upside</b> separate a quality dip from a falling knife.
        <b> Tap a header to sort</b>; tap a row → chart. (Fundamentals fill in over a few seconds.)
      </p>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-[12px]">
          <thead className="text-text-faint border-b border-border">
            <tr>
              <Th k="symbol" label="Sym" />
              <Th k="rsi" label="RSI" />
              <Th k="state" label="Setup" />
              <Th k="dist" label="vs 200" right />
              <Th k="pe" label="P/E" right />
              <Th k="rec" label="Rating" />
              <Th k="upside" label="Upside" right />
              <Th k="cap" label="Mkt Cap" right />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((w) => (
              <tr key={w.symbol} onClick={() => onChart(w.symbol)} className="cursor-pointer transition-colors hover:bg-surface-2/50">
                <td className="px-2.5 py-2 font-semibold text-text-primary">{w.symbol}</td>
                <td className="px-2.5 py-2 font-mono tabular-nums text-text-secondary">{w.rsi}</td>
                <td className="px-2.5 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${bwTone(w.state)}`}>{w.state_label}</span>
                </td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums text-text-faint">
                  {w.dist_200ma_pct != null ? `${w.dist_200ma_pct > 0 ? "+" : ""}${w.dist_200ma_pct}%` : "—"}
                </td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums text-text-secondary">{w.fund?.pe ?? "—"}</td>
                <td className="px-2.5 py-2 text-text-muted">{bwRec(w.fund?.rec)}</td>
                <td className={`px-2.5 py-2 text-right font-mono tabular-nums ${(w.fund?.target_upside_pct ?? 0) > 0 ? "text-bullish-text" : "text-text-faint"}`}>
                  {w.fund?.target_upside_pct != null ? `${w.fund.target_upside_pct > 0 ? "+" : ""}${w.fund.target_upside_pct}%` : "—"}
                </td>
                <td className="px-2.5 py-2 text-right font-mono tabular-nums text-text-muted">{bwCap(w.fund?.mkt_cap)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function TodayPage() {
  const nav = useNavigate();
  const [tab, setTab] = useState<"signals" | "briefing" | "bottom">(() => {
    if (typeof window === "undefined") return "signals";
    // Deep-link from a notification tap: ?tab=reports (the Reports tab id is "briefing").
    const q = new URLSearchParams(window.location.search).get("tab");
    if (q === "reports" || q === "briefing") return "briefing";
    if (q === "bottom") return "bottom";
    if (q === "signals") return "signals";
    return (localStorage.getItem("today_tab") as "signals" | "briefing" | "bottom") || "signals";
  });
  function pickTab(t: "signals" | "briefing" | "bottom") {
    setTab(t);
    try { localStorage.setItem("today_tab", t); } catch { /* ignore */ }
  }
  const [feedStyle, setFeedStyle] = useState<"day_trade" | "swing" | "long_term">("day_trade");

  const { data: alerts } = useAlertsToday();
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  const { data: rank } = useWatchlistRank();
  const { data: scanSignals } = useScanner();

  const goChart = (symbol: string) => nav(`/trading?symbol=${encodeURIComponent(symbol)}`);
  // Day-read stat tile → switch to the Signals tab (where the rail lives) + scroll to its section.
  const jumpToRail = (target: string) => {
    pickTab("signals");
    setTimeout(() => document.getElementById(target)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80);
  };

  // The feed is split into 3 STYLE panels (day-trade / swing / long-term). EVERY alert
  // CLEAN feed — only DELIVERED alerts (what actually reached the user). The not-sent
  // ones (gated + deduped) are kept in the DB and reviewable on the Trading rail's
  // "Review" toggle, so they don't inflate this count or clutter the main feed.
  const feedAll = useMemo(
    () => (alerts ?? [])
      .filter((a) => isFeedSignal(a.alert_type) && !a.user_action && !a.suppressed_reason)
      .sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")),
    [alerts],
  );
  const styleCounts = useMemo(() => {
    const c = { day_trade: 0, swing: 0, long_term: 0 } as Record<string, number>;
    for (const a of feedAll) c[a.style ?? "day_trade"]++;
    return c;
  }, [feedAll]);
  // Group the SELECTED style's alerts by symbol (busy tape → one row per name).
  const groupedSignals = useMemo(() => {
    const m = new Map<string, Alert[]>();
    for (const a of feedAll) {
      if ((a.style ?? "day_trade") !== feedStyle) continue;
      const arr = m.get(a.symbol);
      if (arr) arr.push(a);
      else m.set(a.symbol, [a]);
    }
    return Array.from(m.entries()).map(([symbol, list]) => ({ symbol, list })).slice(0, 15);
  }, [feedAll, feedStyle]);
  const took = useMemo(() => (alerts ?? []).filter((a) => a.user_action === "took"), [alerts]);
  const coiling = useMemo(() => (rank ?? []).filter((r) => r.bucket === "coiling").slice(0, 5), [rank]);
  const leaders = useMemo(() => (rank ?? []).filter((r) => r.bucket === "leader").sort((a, b) => (b.rsi ?? 0) - (a.rsi ?? 0)).slice(0, 5), [rank]);
  const losing = useMemo(() => (rank ?? []).filter((r) => r.bucket === "losing").sort((a, b) => (a.rsi ?? 99) - (b.rsi ?? 99)).slice(0, 5), [rank]);
  // Conviction / long-term ideas the scanner folded in (source != watchlist), at-entry first.
  const ideas = useMemo(
    () => (scanSignals ?? [])
      .filter((s) => s.source && s.source !== "watchlist")
      .sort((a, b) => Number(b.action_label === "Potential Entry") - Number(a.action_label === "Potential Entry"))
      .slice(0, 6),
    [scanSignals],
  );
  const ideasAtEntry = useMemo(() => ideas.filter((s) => s.action_label === "Potential Entry").length, [ideas]);

  const dayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6 pb-16">
        {/* Master Alerts — discoverability (one tap to subscribe to the whole feed) */}
        <MasterAlertsBanner />
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
          {([["signals", "Signals"], ["bottom", "Bottom Watch"], ["briefing", "Reports"]] as const).map(([id, label]) => (
            <button
              key={id}
              onClick={() => pickTab(id)}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 text-[12px] font-semibold rounded-md transition-colors ${
                tab === id ? "bg-surface-4 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              {id === "briefing" && <Bot size={13} />}
              {id === "bottom" && <TrendingDown size={13} />}
              {label}
            </button>
          ))}
        </div>

        {tab === "signals" && (
          <div className="grid gap-6 lg:grid-cols-3 lg:items-start">
            {/* main column — live signals, split into the 3 style panels */}
            <section className="lg:col-span-2">
              <SectionLabel action="Trading" onAction={() => nav("/trading")}>Live signals</SectionLabel>
              <div className="flex items-center gap-1 mb-3 bg-surface-2 rounded-lg p-0.5 w-fit">
                {([["day_trade", "Day Trade"], ["swing", "Swing"], ["long_term", "Long Term"]] as const).map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => setFeedStyle(id)}
                    className={`px-3 py-1 text-[12px] font-semibold rounded-md transition-colors ${
                      feedStyle === id ? "bg-surface-4 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {label} <span className="opacity-60 font-normal">{styleCounts[id] ?? 0}</span>
                  </button>
                ))}
              </div>
              {groupedSignals.length > 0 ? (
                <div className="space-y-2.5">
                  {groupedSignals.map((g, i) => <SymbolGroup key={g.symbol} symbol={g.symbol} list={g.list} onChart={goChart} defaultOpen={i === 0} />)}
                </div>
              ) : feedAll.length === 0 ? (
                <DayRead spy={spy} btc={btc} signals={0} ideas={ideas.length} coiling={coiling} leaders={leaders} losing={losing} onJump={jumpToRail} />
              ) : (
                <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
                  No {feedStyle === "day_trade" ? "day-trade" : feedStyle === "swing" ? "swing" : "long-term"} alerts in this session yet.
                </div>
              )}
            </section>

            {/* side column — worth watching + your day */}
            <div className="space-y-6">
              {ideas.length > 0 && (
                <section id="rail-ideas">
                  <SectionLabel>Trade ideas · {ideasAtEntry > 0 ? `${ideasAtEntry} at entry` : "approaching entry"}</SectionLabel>
                  <div className="space-y-1.5">
                    {ideas.map((s) => <IdeaRow key={s.symbol} s={s} onChart={goChart} />)}
                  </div>
                </section>
              )}
              {coiling.length > 0 && (
                <section id="rail-coiling">
                  <SectionLabel>Next entries · coiling for a long</SectionLabel>
                  <div className="space-y-1.5">
                    {coiling.map((w) => <RankRow key={w.symbol} w={w} onChart={goChart} />)}
                  </div>
                </section>
              )}
              {leaders.length > 0 && (
                <section id="rail-leaders">
                  <SectionLabel>Leaders · strong but extended</SectionLabel>
                  <div className="space-y-1.5">
                    {leaders.map((w) => <RankRow key={w.symbol} w={w} onChart={goChart} leader />)}
                  </div>
                </section>
              )}
              {losing.length > 0 && (
                <section id="rail-losing">
                  <SectionLabel>Losing trend · trim / exit watch</SectionLabel>
                  <div className="space-y-1.5">
                    {losing.map((w) => <RankRow key={w.symbol} w={w} onChart={goChart} losing />)}
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

        {tab === "bottom" && <BottomWatchBoard onChart={goChart} />}

        {tab === "briefing" && (
          <div>
            <div className="flex items-center gap-2 px-1 mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">{dayLabel}</span>
              <span className="text-[11px] text-text-faint">· premarket + end-of-day — same reports as Telegram</span>
            </div>
            <ReportsView onChart={goChart} />
          </div>
        )}
      </div>
    </div>
  );
}
