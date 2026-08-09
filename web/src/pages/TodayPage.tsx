/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  Two tabs:
 *   • Signals  — the quick entry/exit feed (unchanged).
 *   • Briefing — the AI agent's READ on each alert (the narrative that goes to
 *     Telegram), now surfaced in the app, collapsible per alert. The default
 *     place busy users come to see the "why", not just the numbers.
 *  Its own scroll root (AppLayout <main> is overflow-hidden — see
 *  feedback_page_scroll_container).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, ChevronDown } from "lucide-react";
import { useSpyLiveRegime, useBtcLiveRegime, useMarketReports, useReportDates, useBottomWatch, type BottomWatchItem } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";
import MarketClock from "../components/MarketClock";
import ThemeToggle from "../components/ThemeToggle";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
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

/* ── Market reports: the SAME daily intelligence sent to Telegram — the morning
   Premarket Heat brief (premarket.py) and the EOD Recap (eod.py), persisted by
   triage-agent. Premarket/EOD toggle defaults to whichever dropped most recently. ── */
type SwingPick = {
  symbol: string; pattern?: string; type: string; price: number; buy_point: number;
  buy_range: [number, number]; position: string; stop: number; state?: string; reasons: string[]; score?: number;
};
type DayPick = {
  symbol: string; setup: string; type: string; price: number; entry: number; level: number;
  stop: number; target?: number | null; rsi?: number; position: string; reasons: string[]; score?: number;
};

/* Today's Focus — two sections: SWING (monthly MoBO + RC-H breakouts) and DAY-TRADE
   (liquid mega-caps defending a key level / oversold / near a breakout). Symbol is
   clickable → Trading chart. Falls back to plain text for old (non-JSON) reports;
   reads the legacy `picks` as swing for reports persisted before the two-section split. */
type SwingRow = { symbol: string; entry: number; stop: number; target: number; close: number; level: string; why: string };
type SwingReport = { buckets?: Record<string, SwingRow[]>; bucket_order?: string[]; bucket_title?: Record<string, string>; universe?: number; total?: number };
/* The MERGED swing finder — trend + swing are ONE thing (user 2026-08-08). Renders the
   finalized swing book bucketed by the pattern each name hit (opened above a prior
   week/month high · 30W bounce · 200 SMA hold · base breakout · 8/21 cross · RSI-30) and
   folds the trend "ready at a rising 20 EMA" bucket in at the top. One section, one mental
   model: which stocks are sitting in a swing zone today. */
// Per-bucket visual identity — a color-coded dot + pill so each swing TYPE reads at a
// glance, and a short label for the jump bar. Ordered by the report's bucket_order.
const BUCKET_STYLE: Record<string, { dot: string; pill: string }> = {
  opened_above: { dot: "bg-emerald-400", pill: "bg-emerald-400/10 text-emerald-300" },
  "30w": { dot: "bg-amber-400", pill: "bg-amber-400/10 text-amber-300" },
  sma200: { dot: "bg-teal-400", pill: "bg-teal-400/10 text-teal-300" },
  base_bo: { dot: "bg-sky-400", pill: "bg-sky-400/10 text-sky-300" },
  ema_cross: { dot: "bg-green-400", pill: "bg-green-400/10 text-green-300" },
  rsi30: { dot: "bg-purple-400", pill: "bg-purple-400/10 text-purple-300" },
  ma_hold: { dot: "bg-slate-400", pill: "bg-slate-400/10 text-slate-300" },
};
const BUCKET_FALLBACK = { dot: "bg-slate-400", pill: "bg-slate-400/10 text-slate-300" };
const BUCKET_SHORT: Record<string, string> = {
  opened_above: "PWH/PMH reclaim", "30w": "30W bounce", sma200: "200 SMA",
  base_bo: "Base breakout", ema_cross: "8/21 cross", rsi30: "RSI-30", ma_hold: "MA hold",
};
const bStyle = (b: string) => BUCKET_STYLE[b] ?? BUCKET_FALLBACK;

function SwingSetups({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: SwingReport | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const buckets = parsed?.buckets ?? {};
  const order = (parsed?.bucket_order ?? Object.keys(buckets)).filter((b) => (buckets[b] ?? []).length > 0);
  const titles = parsed?.bucket_title ?? {};
  const total = order.reduce((n, b) => n + (buckets[b] ?? []).length, 0);
  if (order.length === 0) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">No name is in a swing zone today — the scan runs after the close (~4:25 PM ET).</div>;
  }
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const card = (x: SwingRow, b: string) => {
    const cell = (label: string, val: number | string, tone: string) => (
      <div><div className="text-[8.5px] font-medium uppercase tracking-wide text-text-faint">{label}</div><div className={`font-mono text-[12px] ${tone}`}>{val}</div></div>
    );
    return (
      <button key={x.symbol + x.level} onClick={() => onChart(x.symbol)} className="group text-left rounded-xl border border-border-subtle bg-surface-1 p-3 transition-colors hover:border-accent hover:bg-surface-2/40">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-[13px] font-bold text-text-primary">{x.symbol}</span>
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide ${bStyle(b).pill}`}>{x.level}</span>
        </div>
        <div className="mt-2 grid grid-cols-4 gap-1.5">
          {cell("buy", x.entry, "text-bullish-text")}
          {cell("stop", x.stop, "text-bearish-text")}
          {cell("tgt", x.target, "text-text-secondary")}
          {cell("now", x.close, "text-text-muted")}
        </div>
        <p className="mt-2 text-[10.5px] leading-snug text-text-muted">{x.why}</p>
      </button>
    );
  };
  return (
    <div className="space-y-4">
      {/* Jump bar — scan the whole board at a glance, tap a type to scroll to its group. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[11px] font-bold text-text-secondary">{total} swing setup{total === 1 ? "" : "s"}</span>
        {order.map((b) => (
          <button key={b} onClick={() => jump(`swing-${b}`)} className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-1 px-2.5 py-1 text-[10.5px] transition-colors hover:border-accent">
            <span className={`h-1.5 w-1.5 rounded-full ${bStyle(b).dot}`} />
            <span className="text-text-secondary">{BUCKET_SHORT[b] ?? b}</span>
            <span className="font-mono text-text-faint">{(buckets[b] ?? []).length}</span>
          </button>
        ))}
      </div>
      <p className="text-[11px] leading-snug text-text-faint">The swing finder — which names are sitting in a swing zone today, scanned on the master universe{parsed?.universe ? ` (${parsed.universe} names)` : ""}. Educational, not financial advice.</p>
      {order.map((b) => {
        const [headline, sub] = (titles[b] ?? b).split(" · ");
        return (
          <section key={b} id={`swing-${b}`} className="scroll-mt-4 space-y-2">
            <div className="flex items-center gap-2 border-b border-border-subtle/60 pb-1.5">
              <span className={`h-2 w-2 shrink-0 rounded-full ${bStyle(b).dot}`} />
              <h3 className="text-[11px] font-bold uppercase tracking-wide text-text-secondary">{headline}</h3>
              {sub && <span className="hidden truncate text-[10px] text-text-faint sm:inline">· {sub}</span>}
              <span className={`ml-auto shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${bStyle(b).pill}`}>{(buckets[b] ?? []).length}</span>
            </div>
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">{(buckets[b] ?? []).map((x) => card(x, b))}</div>
          </section>
        );
      })}
    </div>
  );
}

type PmSignal = { symbol: string; alert_type: string; entry: number; level: number; stop: number; note: string; price: number; gap_pct: number };
const PM_LABEL: Record<string, string> = {
  cml_reclaim: "reclaimed month low", cml_held: "held month low",
  staged_pdl_held: "held prior-day low", staged_pwl_held: "held prior-week low", staged_pml_held: "held prior-month low",
  staged_pdh_break: "broke prior-day high", staged_pwh_break: "broke prior-week high",
  weekly_10w_held: "held 10-week MA", weekly_30w_held: "held 30-week MA",
};
/** Compact "moving premarket" strip — premarket-signal names as chips, shown at the
 *  TOP of Today's Focus (merged in; no longer its own section). Null when nothing's moving. */
function PremarketStrip({ body, onChart }: { body?: string | null; onChart: (s: string) => void }) {
  let sigs: PmSignal[] = [];
  try { sigs = (body ? (JSON.parse(body).signals as PmSignal[]) : []) ?? []; } catch { sigs = []; }
  if (sigs.length === 0) return null;
  // ONE per symbol (a name can tag several levels — prefer a breakout over a hold),
  // ranked by move size so the biggest movers lead, capped so it's focusable not a dump.
  const bySym = new Map<string, PmSignal>();
  for (const s of sigs) {
    const cur = bySym.get(s.symbol.toUpperCase());
    if (!cur || (s.alert_type.includes("break") && !cur.alert_type.includes("break"))) {
      bySym.set(s.symbol.toUpperCase(), s);
    }
  }
  // UPSIDE only (user 2026-07-07) — a premarket breakout gapping UP is momentum; a name that tagged
  // a level but is red in premarket isn't what we want. Rank by the biggest gain.
  const ranked = [...bySym.values()].filter((s) => s.gap_pct > 0).sort((a, b) => b.gap_pct - a.gap_pct);
  const TOP = 6;
  const top = ranked.slice(0, TOP);
  const more = ranked.length - top.length;
  if (top.length === 0) return null;
  return (
    <div className="rounded-xl border border-accent/25 bg-accent/5 p-3">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-accent">📡 Premarket upside · top {top.length} of {ranked.length}</div>
      <div className="flex flex-wrap gap-1.5">
        {top.map((s) => (
          <button
            key={s.symbol}
            onClick={() => onChart(s.symbol)}
            title={`${PM_LABEL[s.alert_type] ?? s.alert_type} · entry $${s.entry} · stop $${s.stop}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-1 px-2.5 py-1 text-[11px] transition-colors hover:border-accent"
          >
            <b className="text-text-primary">{s.symbol}</b>
            <span className={`font-semibold ${s.gap_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{s.gap_pct >= 0 ? "+" : ""}{s.gap_pct}%</span>
            <span className="text-text-faint">{PM_LABEL[s.alert_type] ?? s.alert_type}</span>
          </button>
        ))}
        {more > 0 && <span className="inline-flex items-center px-2 py-1 text-[11px] text-text-faint">+{more} more</span>}
      </div>
    </div>
  );
}

/** Morning Spotlight — the single best pick as a hero card (top swing leader, else
 *  the top day trade). Pulls the real pick data; target = the day-trade's target, or
 *  a 2R measured move for a swing (no target in the report). Null when no picks. */
type RankedPick = {
  kind: "swing" | "day"; symbol: string; price: number; entry: number;
  zone: [number, number] | null; stop: number; target: number; reasons: string[];
  headline: string; isSwing: boolean; score: number;
};

// Combine swing + day-trade picks into ONE ranked list (by the morning engine's score) so we can
// surface just the top 3 as spotlights — no stale full grid that's invalidated by the open.
function rankedPicks(body?: string | null): RankedPick[] {
  let parsed: { swing?: SwingPick[]; daytrade?: DayPick[]; picks?: SwingPick[] } | null = null;
  try { parsed = body ? JSON.parse(body) : null; } catch { parsed = null; }
  if (!parsed) return [];
  const out: RankedPick[] = [];
  for (const s of parsed.swing ?? parsed.picks ?? []) {
    const risk = Math.max(s.buy_point - s.stop, 0.01);
    out.push({ kind: "swing", symbol: s.symbol, price: s.price, entry: s.buy_point, zone: s.buy_range ?? null, stop: s.stop, target: s.buy_point + 2 * risk, reasons: s.reasons ?? [], headline: s.pattern ? `${s.pattern} \u2014 at the buy point` : "Swing leader at the buy point", isSwing: true, score: s.score ?? 0 });
  }
  for (const d of parsed.daytrade ?? []) {
    const risk = Math.max(d.entry - d.stop, 0.01);
    out.push({ kind: "day", symbol: d.symbol, price: d.price, entry: d.entry, zone: null, stop: d.stop, target: d.target != null ? d.target : d.entry + 2 * risk, reasons: d.reasons ?? [], headline: d.setup ?? "Day-trade leader at a key level", isSwing: false, score: d.score ?? 0 });
  }
  return out.sort((a, b) => b.score - a.score);
}

function SpotlightCard({ it, rank, onChart }: { it: RankedPick; rank: number; onChart: (s: string) => void }) {
  const risk = Math.max(it.entry - it.stop, 0.01);
  const rr = (it.target - it.entry) / risk;
  const away = ((it.price - it.entry) / it.entry) * 100;
  const Tile = ({ k, v, tone }: { k: string; v: string; tone?: string }) => (
    <div className="rounded-lg bg-surface-1 p-2">
      <div className="text-[9px] uppercase tracking-wide text-text-faint">{k}</div>
      <div className={`font-mono text-[15px] font-bold ${tone ?? "text-text-primary"}`}>{v}</div>
    </div>
  );
  const Cell = ({ k, v, tone }: { k: string; v: string; tone: string }) => (
    <div className="bg-surface-1 p-2">
      <div className="text-[8px] uppercase tracking-wide text-text-faint">{k}</div>
      <div className={`font-mono text-[12px] font-bold ${tone}`}>{v}</div>
    </div>
  );
  return (
    <button onClick={() => onChart(it.symbol)} className="block w-full overflow-hidden rounded-xl border border-accent/40 bg-accent/5 text-left transition-colors hover:border-accent/60">
      <div className="flex items-center gap-2 border-b border-accent/20 bg-accent/10 px-3.5 py-2.5">
        <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] font-bold text-bg-base">#{rank}</span>
        <span className="font-display text-[16px] font-bold text-text-primary">{it.symbol}</span>
        <span className="truncate text-[12px] text-text-muted">{it.headline}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1.5">
          <span className="rounded border border-bullish-muted bg-bullish-subtle px-1.5 py-0.5 text-[10px] font-bold text-bullish-text">LONG</span>
          <span className="rounded bg-surface-3 px-1.5 py-0.5 text-[10px] font-bold text-text-secondary">{it.isSwing ? "SWING" : "DAY"}</span>
        </span>
      </div>
      <div className="space-y-3 p-3.5">
        <div className="grid grid-cols-3 gap-2">
          <Tile k={`${it.symbol} now`} v={`$${it.price?.toFixed(2)}`} />
          <Tile k={it.isSwing ? "Buy point" : "Entry"} v={`$${it.entry.toFixed(2)}`} tone="text-warning-text" />
          <Tile k="Away" v={`${away >= 0 ? "+" : ""}${away.toFixed(1)}%`} tone={away >= 0 ? "text-bullish-text" : "text-text-muted"} />
        </div>
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-surface-3 sm:grid-cols-4">
          <Cell k={it.isSwing ? "Buy zone" : "Entry"} v={it.zone ? `$${it.zone[0].toFixed(2)}\u2013${it.zone[1].toFixed(2)}` : `$${it.entry.toFixed(2)}`} tone="text-warning-text" />
          <Cell k="Target" v={`$${it.target.toFixed(2)}`} tone="text-bullish-text" />
          <Cell k="Stop" v={`$${it.stop.toFixed(2)}`} tone="text-bearish-text" />
          <Cell k="Risk / Reward" v={`${rr.toFixed(1)}R`} tone="text-bullish-text" />
        </div>
        {it.reasons.length > 0 && <p className="text-[11px] leading-snug text-text-muted">{it.reasons.slice(0, 2).join(" \u00b7 ")}</p>}
      </div>
    </button>
  );
}

function TopSpotlights({ body, onChart }: { body?: string | null; onChart: (s: string) => void }) {
  let market_ok: boolean | undefined;
  try { market_ok = body ? JSON.parse(body).market_ok : undefined; } catch { market_ok = undefined; }
  const top = rankedPicks(body).slice(0, 3);
  if (!top.length) return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center">
      <p className="text-[13px] font-semibold text-text-secondary">No spotlight setups right now</p>
      <p className="mt-1 text-[11px] leading-snug text-text-faint">Nothing gapping over yesterday's high or reclaiming a level — better empty than a forced pick. Watch the premarket movers below.</p>
    </div>
  );
  return (
    <div className="space-y-2.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wide text-accent">☀️ Top 3 spotlights</span>
        {market_ok !== undefined && <span className={`text-[11px] font-semibold ${market_ok ? "text-bullish-text" : "text-bearish-text"}`}>{market_ok ? "\ud83d\udfe2 healthy \u2014 size up" : "\ud83d\udd34 weak \u2014 half size"}</span>}
      </div>
      {top.map((it, i) => <SpotlightCard key={it.symbol + it.kind} it={it} rank={i + 1} onChart={onChart} />)}
    </div>
  );
}

function ReportsView({ onChart }: { onChart: (s: string) => void }) {
  const nav = useNavigate();
  // View state survives navigation (open a chart → back) via sessionStorage — otherwise a
  // remount collapses every section + resets the session and you'd re-expand every time.
  const [selectedDate, setSelectedDate] = useState(() => sessionStorage.getItem("today.date") ?? "");
  const { data, isLoading } = useMarketReports(selectedDate || undefined);
  const { data: datesData } = useReportDates();
  const reportDates = datesData?.dates ?? [];
  const fmtDate = (d: string) =>
    new Date(d + "T00:00:00").toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  const pre = data?.premarket ?? null;
  const eod = data?.eod ?? null;
  const mf = data?.morning_focus ?? null;
  const sw = data?.swing_setups ?? null;
  const ps = data?.premarket_signals ?? null;
  // Timeline rail: which section is active (scroll target). No tab state — every
  // report renders in one scroll, in the order it drops through the day.
  const [activeSec, setActiveSec] = useState<string>(() => sessionStorage.getItem("today.active") ?? "sec-focus");
  // Collapsible cards — collapsed by default for less context; Today's Focus (the
  // actionable core) starts open. Jumping from the rail also expands the target.
  const [openSecs, setOpenSecs] = useState<Set<string>>(() => {
    try { const raw = sessionStorage.getItem("today.open"); if (raw) return new Set<string>(JSON.parse(raw)); } catch { /* ignore */ }
    return new Set(["sec-focus"]);
  });
  // Persist view state so returning from the chart page lands you exactly where you were.
  useEffect(() => { sessionStorage.setItem("today.date", selectedDate); }, [selectedDate]);
  useEffect(() => { sessionStorage.setItem("today.active", activeSec); }, [activeSec]);
  useEffect(() => { sessionStorage.setItem("today.open", JSON.stringify([...openSecs])); }, [openSecs]);
  // One-time scroll restore once the reports render — return to the section you left open.
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || isLoading || !data) return;
    restored.current = true;
    if (activeSec && activeSec !== "sec-focus") {
      requestAnimationFrame(() => document.getElementById(activeSec)?.scrollIntoView({ block: "start" }));
    }
  }, [isLoading, data, activeSec]);
  const toggleSec = (id: string) =>
    setOpenSecs((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  if (isLoading) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">Loading reports…</div>;
  }

  const sections = [
    // ── ACTIONABLE CORE — Today's Focus leads (the plays for THIS day). ──
    { id: "sec-focus", time: "8:55a", title: "Today's Focus", present: !!mf || !!ps,
      wait: "Leaders Near a Buy Point drop pre-open (~8:45 AM ET).",
      render: () => (
        <div className="space-y-4">
          {/* Top 3 ranked spotlights + the live premarket movers. No stale full grid — those
              entries invalidate by the open; the ranked spotlights + movers stay actionable. */}
          {mf
            ? <TopSpotlights body={mf.body} onChart={onChart} />
            : <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">Top spotlights drop ~8:55 ET.</div>}
          <PremarketStrip body={ps?.body} onChart={onChart} />
        </div>
      ) },
    // ── CONTEXT — premarket read + EOD recap in ONE card. ──
    { id: "sec-briefing", time: "BRIEF", title: "Briefing", present: !!pre || !!eod,
      wait: "Premarket read ~8:30 AM · EOD recap ~4:05 PM ET.",
      render: () => (
        <div className="space-y-4">
          {pre && <div><div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-accent">Premarket read</div><ReportBody body={pre.body} onChart={onChart} /></div>}
          {eod && <div><div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-amber-400">EOD recap</div><ReportBody body={eod.body} onChart={onChart} /></div>}
          {!pre && !eod && <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">Briefing drops pre-open + after the close.</div>}
        </div>
      ) },
    // ── DISCOVERY — trend + swing merged into ONE finder (which names are in a swing zone). ──
    { id: "sec-swing", time: "AFTER·CLOSE", title: "Swing setups", present: !!sw,
      wait: "The swing finder runs after the close (~4:25 PM ET).",
      render: () => <SwingSetups body={sw?.body ?? ""} onChart={onChart} /> },
    { id: "sec-bottom", time: "ALL·DAY", title: "Bottom watch", present: true,
      wait: "", render: () => <BottomWatchBoard onChart={onChart} /> },
  ];
  const jump = (id: string) => {
    setActiveSec(id);
    setOpenSecs((prev) => new Set(prev).add(id));   // jumping opens the card
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-[190px_1fr]">
      {/* Timeline rail — the day's reports in order; click to jump. */}
      <nav className="hidden self-start md:sticky md:top-2 md:block">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide text-text-muted">🕘 Your Day</div>
        <div className="space-y-0.5">
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => jump(s.id)}
              className={`w-full rounded-lg border-l-2 px-2.5 py-2 text-left transition-colors ${activeSec === s.id ? "border-accent bg-accent/10" : "border-transparent hover:bg-surface-2"}`}
            >
              <div className="font-mono text-[9px] uppercase tracking-wide text-text-faint">{s.time}</div>
              <div className="flex items-center gap-1.5 text-[12px] font-semibold text-text-secondary">
                {s.present ? <span className="text-bullish-text">✓</span> : <span className="text-text-faint">—</span>}
                {s.title}
              </div>
            </button>
          ))}
        </div>

        {/* Live now — the signal feed lives on the Trading page only. */}
        <button
          onClick={() => nav("/trading")}
          className="mt-3 flex w-full flex-col gap-0.5 rounded-lg border border-accent/25 bg-accent/5 p-2.5 text-left transition-colors hover:border-accent/50"
        >
          <span className="text-[11px] font-bold text-accent">⚡ Live now</span>
          <span className="text-[11px] font-semibold text-accent">Open Trading →</span>
        </button>

        {reportDates.length > 0 && (
          <div className="mt-3">
            <label className="mb-1 block font-mono text-[9px] uppercase tracking-wide text-text-faint">Session</label>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              title="Review a past session"
              className="w-full rounded-lg border border-border-subtle bg-surface-2 px-2 py-1.5 text-[11px] text-text-secondary"
            >
              <option value="">Latest</option>
              {reportDates.map((d) => (
                <option key={d} value={d}>{fmtDate(d)}</option>
              ))}
            </select>
          </div>
        )}

        <p className="mt-3 text-[10px] leading-snug text-text-faint">✓ published · — publishes after the close. Same reports as Telegram, reviewable by session.</p>
      </nav>

      {/* Content — every report section in one scroll. */}
      <div className="min-w-0 space-y-8">
        {/* Mobile session picker — the desktop one lives in the rail (hidden on mobile). */}
        {reportDates.length > 0 && (
          <div className="flex items-center gap-2 md:hidden">
            <label className="font-mono text-[9px] uppercase tracking-wide text-text-faint">Session</label>
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              title="Review a past session"
              className="rounded-lg border border-border-subtle bg-surface-2 px-2 py-1.5 text-[11px] text-text-secondary"
            >
              <option value="">Latest</option>
              {reportDates.map((d) => (
                <option key={d} value={d}>{fmtDate(d)}</option>
              ))}
            </select>
          </div>
        )}
        {sections.map((s) => {
          const open = openSecs.has(s.id);
          return (
            <section key={s.id} id={s.id} className="scroll-mt-4">
              {/* collapsible header — tap to expand/collapse (collapsed = less context) */}
              <button
                type="button"
                onClick={() => toggleSec(s.id)}
                aria-expanded={open}
                className="mb-2.5 flex w-full items-center gap-2 text-left"
              >
                <span className="font-mono text-[10px] uppercase tracking-wide text-text-faint">{s.time}</span>
                <h2 className="text-[13px] font-bold text-text-primary">{s.title}</h2>
                {s.present ? <span className="text-[10px] text-bullish-text">✓</span> : <span className="text-[10px] text-text-faint">—</span>}
                <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-text-faint transition-transform ${open ? "rotate-180" : ""}`} />
              </button>
              {open && (s.present ? s.render() : (
                <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">{s.wait}</div>
              ))}
            </section>
          );
        })}
      </div>
    </div>
  );
}

/** Linkify a ticker token (an uppercase symbol immediately followed by a "$" price,
 *  e.g. "MSTR $98.70") → a clickable chart link, without disturbing the monospace
 *  layout (inline, no padding). Non-ticker uppercase words (RSI, ADX, MA…) aren't
 *  followed by a "$", so they're left alone. */
function Linked({ text, onChart }: { text: string; onChart: (s: string) => void }) {
  const parts = text.split(/(\b[A-Z]{2,5}\b)(?=\s*\$)/g);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <button key={i} onClick={() => onChart(p)} className="inline text-accent hover:underline">{p}</button>
          : <span key={i}>{p}</span>,
      )}
    </>
  );
}

/** Render a Telegram-HTML report body (premarket brief / EOD recap) as readable
 *  STRUCTURE — bold section headers, monospace cards for the <pre> tables, and plain
 *  prose. Tickers ("MSTR $98.70") link to the chart. Our own content only. */
function ReportBody({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  if (!body || !body.trim()) return null;
  const strip = (s: string) => s.replace(/<\/?(b|strong|i|em|code)>/gi, "");
  const parts = body.split(/(<pre>[\s\S]*?<\/pre>)/g).filter((p) => p.trim() !== "");
  return (
    <div className="max-w-3xl space-y-1.5 rounded-xl border border-border-subtle bg-surface-1 p-4">
      {parts.map((part, i) => {
        if (part.startsWith("<pre>")) {
          return (
            <pre key={i} className="overflow-x-auto whitespace-pre rounded-lg border border-border-subtle bg-surface-2 p-2.5 font-mono text-[12px] leading-relaxed text-text-secondary"><Linked text={strip(part.replace(/<\/?pre>/g, ""))} onChart={onChart} /></pre>
          );
        }
        return part.split("\n").filter((l) => l.trim() !== "").map((line, j) => {
          const t = line.trim();
          const isHeader = /^(<b>|<strong>).*(<\/b>|<\/strong>)$/i.test(t);
          return isHeader
            ? <div key={`${i}-${j}`} className="pt-1.5 text-[13px] font-bold text-text-primary">{strip(t)}</div>
            : <p key={`${i}-${j}`} className="text-[13px] leading-relaxed text-text-secondary"><Linked text={strip(t)} onChart={onChart} /></p>;
        });
      })}
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
  const { data: spy } = useSpyLiveRegime();
  const { data: btc } = useBtcLiveRegime();
  const goChart = (symbol: string) => nav(`/trading?symbol=${encodeURIComponent(symbol)}`);

  const dayLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8 py-6 pb-16">
        {/* status strip — live market clock + theme toggle (same shell as Trading) */}
        <div className="mb-4 flex items-center gap-3 border-b border-border-subtle pb-3">
          <MarketClock />
          <div className="ml-auto"><ThemeToggle /></div>
        </div>
        {/* market read + posture */}
        <header className="pb-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h1 className="font-display text-lg font-semibold text-text-primary">{greeting()}</h1>
            <div className="flex items-center gap-2">
              <RegimeChip label="SPY" r={spy} />
              <RegimeChip label="BTC" r={btc} />
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-text-muted">
            <span className="font-mono text-[11px] uppercase tracking-wide text-text-faint">{dayLabel}</span>
            <span className="inline-flex items-center gap-1.5">
              <ShieldCheck size={13} className="text-text-faint" /> Stops on every position ·{" "}
              <span className={spy?.below_pdl ? "text-warning-text font-medium" : "text-bullish-text font-medium"}>
                {spy?.below_pdl ? "Defensive" : "Normal"}
              </span>
            </span>
          </div>
          <p className="mt-1 text-[12px] text-text-faint">Your trading day, top to bottom — premarket to the close.</p>
        </header>

        {/* Today = the briefing timeline. The live signal feed lives on the Trading
            page only; here it's plan + reports, top to bottom, premarket → close. */}
        <ReportsView onChart={goChart} />
      </div>
    </div>
  );
}
