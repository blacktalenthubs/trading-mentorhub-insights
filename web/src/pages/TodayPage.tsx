/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  Two tabs:
 *   • Signals  — the quick entry/exit feed (unchanged).
 *   • Briefing — the AI agent's READ on each alert (the narrative that goes to
 *     Telegram), now surfaced in the app, collapsible per alert. The default
 *     place busy users come to see the "why", not just the numbers.
 *  Its own scroll root (AppLayout <main> is overflow-hidden — see
 *  feedback_page_scroll_container).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, ChevronDown, Star } from "lucide-react";
import { useSpyLiveRegime, useBtcLiveRegime, useMarketReports, useReportDates, useToggleWatchlistFocus, useWatchlist } from "../api/hooks";
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
  ema_cross: { dot: "bg-green-400", pill: "bg-green-400/10 text-green-300" },
  rsi30: { dot: "bg-purple-400", pill: "bg-purple-400/10 text-purple-300" },
  ma_hold: { dot: "bg-slate-400", pill: "bg-slate-400/10 text-slate-300" },
};
const BUCKET_FALLBACK = { dot: "bg-slate-400", pill: "bg-slate-400/10 text-slate-300" };
const BUCKET_SHORT: Record<string, string> = {
  opened_above: "PWH/PMH reclaim", "30w": "30W bounce", sma200: "200 SMA",
  ema_cross: "8/21 cross", rsi30: "RSI-30", ma_hold: "MA hold",
};
const bStyle = (b: string) => BUCKET_STYLE[b] ?? BUCKET_FALLBACK;

function SwingSetups({ body, onChart, exclude = [] }: { body: string; onChart: (s: string) => void; exclude?: string[] }) {
  let parsed: SwingReport | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const buckets = parsed?.buckets ?? {};
  // Momentum view drops the oversold/support buckets (rsi30, sma200, ma_hold) — those live
  // in the "At Support / Oversold" board now, so a name never shows in two sections.
  const order = (parsed?.bucket_order ?? Object.keys(buckets))
    .filter((b) => !exclude.includes(b))
    .filter((b) => (buckets[b] ?? []).length > 0);
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
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">{(buckets[b] ?? []).slice(0, 6).map((x) => card(x, b))}</div>
          </section>
        );
      })}
    </div>
  );
}

type GapRow = { sym: string; dir?: string; gap_pct: number; open?: number; prev_close?: number; bias?: string;
  or?: { or_high: number; or_low: number; last: number; state: string } | null;
  gap_dir?: string; days_ago?: number; direction?: string; trigger?: number; stop?: number;
  to_trigger_pct?: number; risk_pct?: number; context?: string };
function GapSetups({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  const toggleFocus = useToggleWatchlistFocus();
  const { data: wl } = useWatchlist();
  const focused = new Set((wl ?? []).filter((w) => w.focus).map((w) => w.symbol));
  const [openB, setOpenB] = useState<Set<string>>(() => new Set(["gap-up", "gap-dn", "t321-long", "t321-short"]));
  const toggle = (k: string) => setOpenB((prev) => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  let parsed: { gaps?: GapRow[]; setups?: GapRow[]; scanned?: number } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const gaps = parsed?.gaps ?? [];
  const setups = parsed?.setups ?? [];
  if (gaps.length === 0 && setups.length === 0) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">No big gaps or 3-2-1 setups right now — the gap scan runs premarket (analytics/gap_scanner.py).</div>;
  }
  const star = (s: string) => { const isFav = focused.has(s); return (
    <button title={isFav ? `${s} in Focus — click to remove` : `Add ${s} to Focus`} aria-label={isFav ? `Remove ${s} from Focus` : `Add ${s} to Focus`} onClick={() => toggleFocus.mutate(s)} className={`rounded p-1 transition-colors hover:bg-surface-2 ${isFav ? "text-amber-400" : "text-text-faint hover:text-amber-400"}`}><Star className={`h-3.5 w-3.5 ${isFav ? "fill-amber-400" : ""}`} /></button>
  ); };
  const symBtn = (s: string) => <button onClick={() => onChart(s)} className="font-mono text-[13px] font-bold text-text-primary hover:text-accent">{s}</button>;
  const gapCard = (g: GapRow) => {
    const up = (g.dir ?? "").toUpperCase() === "UP";
    return (
      <div key={g.sym} className="rounded-xl border border-border-subtle bg-surface-1 p-3 transition-colors hover:border-accent">
        <div className="flex items-center justify-between gap-2">
          {symBtn(g.sym)}
          <div className="flex items-center gap-1.5">
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase ${up ? "border-bullish-muted bg-bullish-subtle text-bullish-text" : "border-bearish-muted bg-bearish-subtle text-bearish-text"}`}>GAP {g.dir} {g.gap_pct > 0 ? "+" : ""}{g.gap_pct}%</span>
            {star(g.sym)}
          </div>
        </div>
        <button onClick={() => onChart(g.sym)} className="mt-1.5 block w-full text-left text-[10.5px] text-text-muted">
          {g.or ? <span>OR <span className="font-mono">{g.or.or_low}–{g.or.or_high}</span> → <span className="text-text-secondary">{g.or.state}</span></span>
            : <span className="text-text-faint">opening range pending (intraday)</span>}
          {g.bias && <div className="mt-1 text-[9.5px] text-text-faint">{g.bias}</div>}
        </button>
      </div>
    );
  };
  const setupCard = (s: GapRow) => {
    const long = (s.direction ?? "").toUpperCase() === "LONG";
    return (
      <div key={s.sym} className="rounded-xl border border-border-subtle bg-surface-1 p-3 transition-colors hover:border-accent">
        <div className="flex items-center justify-between gap-2">
          {symBtn(s.sym)}
          <div className="flex items-center gap-1.5">
            <span className={`rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase ${long ? "border-bullish-muted bg-bullish-subtle text-bullish-text" : "border-bearish-muted bg-bearish-subtle text-bearish-text"}`}>{s.direction}</span>
            {star(s.sym)}
          </div>
        </div>
        <button onClick={() => onChart(s.sym)} className="mt-1 block w-full text-left">
          <div className="text-[10px] text-text-faint">gap {s.gap_dir} {s.gap_pct && s.gap_pct > 0 ? "+" : ""}{s.gap_pct}% · {s.days_ago}d ago</div>
          <div className="mt-2 grid grid-cols-3 gap-1.5 text-[10px]">
            <div><div className="text-[8.5px] uppercase tracking-wide text-text-faint">{long ? "break >" : "break <"}</div><div className="font-mono text-text-primary">{s.trigger}</div></div>
            <div><div className="text-[8.5px] uppercase tracking-wide text-text-faint">stop</div><div className="font-mono text-bearish-text">{s.stop}</div></div>
            <div><div className="text-[8.5px] uppercase tracking-wide text-text-faint">to trigger</div><div className="font-mono text-text-secondary">{s.to_trigger_pct && s.to_trigger_pct > 0 ? "+" : ""}{s.to_trigger_pct}%</div></div>
          </div>
          {s.context && <div className="mt-1.5 text-[9.5px] text-text-faint">{s.context}</div>}
        </button>
      </div>
    );
  };
  const buckets = [
    { key: "gap-up", title: "Gaps up · OR-high long", bull: true, items: gaps.filter((g) => (g.dir ?? "").toUpperCase() === "UP"), render: gapCard },
    { key: "gap-dn", title: "Gaps down · OR-low short", bull: false, items: gaps.filter((g) => (g.dir ?? "").toUpperCase() === "DOWN"), render: gapCard },
    { key: "t321-long", title: "3-2-1 long · gap-up continuation", bull: true, items: setups.filter((s) => (s.direction ?? "").toUpperCase() === "LONG"), render: setupCard },
    { key: "t321-short", title: "3-2-1 short · gap-down continuation", bull: false, items: setups.filter((s) => (s.direction ?? "").toUpperCase() === "SHORT"), render: setupCard },
  ].filter((b) => b.items.length > 0);
  return (
    <div className="space-y-3">
      <div className="text-[10.5px] text-text-faint">{gaps.length} big gap{gaps.length === 1 ? "" : "s"} · {setups.length} 3-2-1 setup{setups.length === 1 ? "" : "s"}{parsed?.scanned ? ` · scanned ${parsed.scanned}` : ""}</div>
      {buckets.map((b) => {
        const isOpen = openB.has(b.key);
        return (
          <div key={b.key} className="overflow-hidden rounded-xl border border-border-subtle">
            <button onClick={() => toggle(b.key)} className="flex w-full items-center gap-2 bg-surface-2/40 px-3 py-2 text-left transition-colors hover:bg-surface-2/70">
              <span className={`h-2 w-2 shrink-0 rounded-full ${b.bull ? "bg-bullish-text" : "bg-bearish-text"}`} />
              <span className="text-[11px] font-bold uppercase tracking-wide text-text-secondary">{b.title}</span>
              <span className="ml-auto shrink-0 rounded-full bg-surface-1 px-2 py-0.5 text-[10px] font-bold text-text-secondary">{b.items.length}</span>
              <ChevronDown className={`h-4 w-4 shrink-0 text-text-faint transition-transform ${isOpen ? "rotate-180" : ""}`} />
            </button>
            {isOpen && <div className="grid grid-cols-1 gap-2 p-2 lg:grid-cols-2">{b.items.slice(0, 6).map(b.render)}</div>}
          </div>
        );
      })}
      <p className="text-[11px] leading-snug text-text-faint">Big (≥4%) gaps: after the 10-min opening range, long a break of the OR high / short the OR low. 3-2-1 follows the gap: gap UP → long the break of the post-gap high; gap DOWN → short the break of the post-gap low (stop at the gap-day high). Tap a header to expand/collapse, a symbol to open its chart, ★ to add to Focus. Educational, not financial advice.</p>
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
interface SupRow {
  sym: string; price: number; rsi_d: number; rsi_w: number;
  weekly_oversold: boolean; triggers: string[]; levels: string[];
  at_support: boolean; strike: number; dte: number; ambiguous?: boolean;
}
// At Support / Oversold: names bouncing at a support point NOW (rising 20/50, 200 SMA,
// VWAP/POC/VAL, or an RSI reclaim) with the put strike inline, plus the oversold watch
// ladder (under 40 weekly RSI, waiting for the turn). One board — selling a put is just
// what you do at these support points.
function AtSupport({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: { rows?: SupRow[]; scanned?: number } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const rows = parsed?.rows ?? [];
  if (rows.length === 0)
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">Nothing at a support point in the last scan.</div>;
  const atAll = rows.filter((r) => r.at_support);
  const at = atAll.slice(0, 6);   // show the top 6 (rows are already ranked best-first)
  const watch = rows.filter((r) => !r.at_support);
  const rsiCol = (v: number) => (v < 40 ? "text-bullish-text" : "text-text-muted");
  return (
    <div className="space-y-2.5">
      <div className="text-[10.5px] text-text-faint">
        {atAll.length} at support{atAll.length > 6 ? " · top 6" : ""} · {watch.length} on the oversold (RSI&lt;40) watch · scanned {parsed?.scanned ?? "—"} · strike = sell a ~30d put here
      </div>
      {/* AT SUPPORT NOW — the trigger(s) it's bouncing on; the strike to sell on the right. */}
      {at.map((r, i) => (
        <div key={r.sym + i} title={r.levels.join(" · ")} className="flex items-center justify-between gap-2 rounded-lg border border-bullish-text/30 bg-bullish-text/5 px-3 py-2">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <button onClick={() => onChart(r.sym)} className="font-mono text-[13px] font-bold text-text-primary hover:text-accent">{r.sym}</button>
            {r.triggers.map((t) => (
              <span key={t} className="rounded bg-bullish-text/15 px-1.5 py-0.5 text-[9.5px] font-semibold text-bullish-text">{t}</span>
            ))}
            {r.ambiguous && r.triggers.some((t) => /POC|VAL|HVN|VWAP/.test(t)) && (
              <span title="Two near-tied volume nodes — the profile level may differ from your chart. Verify before trading." className="rounded bg-warning-text/15 px-1.5 py-0.5 text-[9.5px] font-semibold text-warning-text">⚠ verify level</span>
            )}
          </div>
          <div className="flex items-center gap-3 whitespace-nowrap font-mono text-[11px] tabular-nums text-text-muted">
            <span className={rsiCol(r.rsi_w)}>RSI d{r.rsi_d}/w{r.rsi_w}</span>
            <span className="text-text-secondary">${r.price.toFixed(2)}</span>
            <span className="font-semibold text-bullish-text">PUT ≤ {r.strike.toFixed(2)} · ~{r.dte}d</span>
          </div>
        </div>
      ))}
      {/* OVERSOLD WATCH — under 40 weekly RSI, not bouncing yet; wait for the turn. */}
      {watch.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-surface-1 p-2.5">
          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wide text-text-muted">Oversold watch (weekly RSI&lt;40 — wait for the turn)</div>
          <div className="flex flex-wrap gap-1.5">
            {watch.map((r) => (
              <button
                key={r.sym}
                onClick={() => onChart(r.sym)}
                title={`weekly RSI ${r.rsi_w} · daily ${r.rsi_d} · $${r.price.toFixed(2)}`}
                className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-2 px-2.5 py-1 text-[11px] transition-colors hover:border-accent"
              >
                <b className="text-text-primary">{r.sym}</b>
                <span className={`font-mono ${rsiCol(r.rsi_w)}`}>w{r.rsi_w}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
// Weekly Value: names AT their weekly volume-profile POC/VWAP/VAL (Robinhood data —
// matches the chart). A name whose CURRENT WEEK opened above the level is holding it as
// support (🛡, tradeable, stop under it); one that opened below is testing from under (🎯).
// 🌟 = FRESH — the prior day was the first close above the level. Top 10, fresh first.
interface WvpRow {
  sym: string; price: number; week_open: number; poc: number; vwap: number; val: number;
  d_poc: number; d_vwap: number; d_val: number; at: string; held: boolean;
  opened_above: boolean; fresh?: boolean; ambiguous?: boolean;
}
function WeeklyValue({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: { rows?: WvpRow[]; scanned?: number; at?: number; held?: number; fresh?: number; weeks?: number } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const rows = parsed?.rows ?? [];
  if (rows.length === 0)
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">No names at their weekly value area in the last scan.</div>;
  const levelVal = (r: WvpRow) => (r.at === "POC" ? r.poc : r.at === "VWAP" ? r.vwap : r.val);
  const away = (r: WvpRow) => (r.at === "POC" ? r.d_poc : r.at === "VWAP" ? r.d_vwap : r.d_val);
  return (
    <div className="space-y-2.5">
      <div className="text-[10.5px] text-text-faint">
        {parsed?.held ?? 0} holding support · {parsed?.fresh ?? 0} fresh reclaim{(parsed?.fresh ?? 0) === 1 ? "" : "s"} · {parsed?.at ?? rows.length} at their weekly POC/VWAP/VAL · {parsed?.weeks ?? 156}w profile · opened-above = support beneath you
      </div>
      {rows.map((r, i) => {
        const holdColor = r.held ? "border-bullish-text/30 bg-bullish-text/5" : "border-warning-text/30 bg-warning-text/5";
        return (
          <div key={r.sym + i} className={`flex items-center justify-between gap-2 rounded-lg border px-3 py-2 ${holdColor}`}>
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <button onClick={() => onChart(r.sym)} className="font-mono text-[13px] font-bold text-text-primary hover:text-accent">{r.sym}</button>
              {r.fresh && <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[9.5px] font-semibold text-accent">🌟 NEW</span>}
              <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-semibold ${r.held ? "bg-bullish-text/15 text-bullish-text" : "bg-warning-text/15 text-warning-text"}`}>
                {r.held ? `holding ${r.at}` : `testing ${r.at}`}
              </span>
              {r.ambiguous && <span title="Two near-tied volume nodes — verify the level on your chart." className="rounded bg-warning-text/15 px-1.5 py-0.5 text-[9.5px] font-semibold text-warning-text">⚠ verify</span>}
            </div>
            <div className="flex items-center gap-3 whitespace-nowrap font-mono text-[11px] tabular-nums text-text-muted">
              <span title="this week's open">o {r.week_open.toFixed(2)}</span>
              <span className="text-text-secondary">${r.price.toFixed(2)}</span>
              <span className={r.held ? "font-semibold text-bullish-text" : "font-semibold text-warning-text"}>{r.at} {levelVal(r).toFixed(2)} · {away(r) >= 0 ? "+" : ""}{away(r).toFixed(1)}%</span>
            </div>
          </div>
        );
      })}
      <div className="text-[10px] text-text-faint">Weekly volume profile from Robinhood (matches TradingView). Educational, not financial advice — verify on your chart.</div>
    </div>
  );
}
interface BreakoutRow {
  ticker: string; pattern: string; stage: string; buy_point: number; last_close: number;
  pct_to_buy: number | null; suggested_stop: number; risk_pct: number | null; rvol: number;
  volume_ok: boolean; base_depth_pct: number; base_length_days: number; rsi14: number | null;
  dist_from_200sma_pct: number | null; score: number; reason: string;
}
const BREAKOUT_LABEL: Record<string, string> = {
  cup_handle: "Cup & Handle", flat_base: "Flat Base", ascending_triangle: "Asc. Triangle",
  bull_flag: "Bull Flag", horizontal_tba: "TBA breakout", trendline_break: "Trendline break",
};
function Breakouts({ body, onChart }: { body: string; onChart: (s: string) => void }) {
  let parsed: { rows?: BreakoutRow[]; empty?: boolean } | null = null;
  try { parsed = JSON.parse(body); } catch { parsed = null; }
  const rows = parsed?.rows ?? [];
  if (rows.length === 0)
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">No qualified breakout setups today.</div>;
  const nBreak = rows.filter((r) => r.stage === "breakout").length;
  return (
    <div className="space-y-2.5">
      <div className="text-[10.5px] text-text-faint">{nBreak} breaking out · {rows.length - nBreak} forming · TBA = buy trigger, max stop = invalidation. Educational — verify on your chart.</div>
      {rows.map((r, i) => {
        const brk = r.stage === "breakout";
        return (
          <div key={r.ticker + r.pattern + i} className={`rounded-lg border px-3 py-2 ${brk ? "border-bullish-text/30 bg-bullish-text/5" : "border-warning-text/25 bg-warning-text/5"}`}>
            <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <button onClick={() => onChart(r.ticker)} className="font-mono text-[13px] font-bold text-text-primary hover:text-accent">{r.ticker}</button>
                <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[9.5px] font-semibold text-text-secondary">{BREAKOUT_LABEL[r.pattern] ?? r.pattern}</span>
                <span className={`rounded px-1.5 py-0.5 text-[9.5px] font-semibold ${brk ? "bg-bullish-text/15 text-bullish-text" : "bg-warning-text/15 text-warning-text"}`}>{brk ? `▲ breakout ${r.rvol}x` : "forming"}</span>
                {!r.volume_ok && brk && <span title="Broke the level but volume was light — borderline." className="rounded bg-warning-text/15 px-1.5 py-0.5 text-[9.5px] font-semibold text-warning-text">⚠ light vol</span>}
              </div>
              <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[10px] font-bold text-accent">{r.score}</span>
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[11px] tabular-nums text-text-muted">
              <span>TBA <b className="text-text-secondary">${r.buy_point.toFixed(2)}</b>{r.pct_to_buy != null && <span className="text-text-faint"> ({r.pct_to_buy >= 0 ? "+" : ""}{r.pct_to_buy}%)</span>}</span>
              <span>stop <span className="text-bearish-text">${r.suggested_stop.toFixed(2)}</span></span>
              {r.risk_pct != null && <span>risk {r.risk_pct}%</span>}
              <span className="text-text-faint">${r.last_close.toFixed(2)}</span>
            </div>
            <div className="mt-0.5 text-[10.5px] text-text-faint">{r.reason}</div>
          </div>
        );
      })}
    </div>
  );
}
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
  // Spotlight only the SOLID ones: a real ≥2R reward and still near the entry (not already
  // chased away from it). Ranked by the engine score, capped at 6. Fewer on a thin day.
  const top = rankedPicks(body).filter((p) => {
    const risk = Math.max(p.entry - p.stop, 0.01);
    const rr = (p.target - p.entry) / risk;
    const away = ((p.price - p.entry) / p.entry) * 100;
    return rr >= 2 && Math.abs(away) <= 4;
  }).slice(0, 6);
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
  const mf = data?.morning_focus ?? null;
  const sw = data?.swing_setups ?? null;
  const gap = data?.gap_setups ?? null;
  const sup = data?.support ?? null;
  const wvp = data?.weekly_vp ?? null;
  const bo = data?.breakout_setups ?? null;
  const ps = data?.premarket_signals ?? null;
  // Timeline rail: which section is active (scroll target). No tab state — every
  // report renders in one scroll, in the order it drops through the day.
  const [activeSec, setActiveSec] = useState<string>(() => sessionStorage.getItem("today.active") ?? "sec-focus");
  // Collapsible cards — collapsed by default for less context; Today's Focus (the
  // actionable core) starts open. Jumping from the rail also expands the target.
  const [openSecs, setOpenSecs] = useState<Set<string>>(() => {
    try { const raw = sessionStorage.getItem("today.open"); if (raw) return new Set<string>(JSON.parse(raw)); } catch { /* ignore */ }
    return new Set(["sec-focus", "sec-support"]);
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
    { id: "sec-focus", group: "Plays", time: "8:55a", title: "Today's Focus", present: !!mf || !!ps,
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
    // ── AT SUPPORT / OVERSOLD — ONE board: rising 20/50 & 200 SMA, VWAP/POC/VAL, RSI
    //    reclaims, each with the put strike. Absorbs the old put-sellers, bottom-watch,
    //    volume-signals and 20-MA sections so a name shows in exactly one place. ──
    { id: "sec-support", group: "Buy the dip", time: "INTRADAY", title: "At Support · Oversold", present: !!sup,
      wait: "Run analytics/support_scan.py — rising 20/50 & 200 SMA, VWAP/POC/VAL, RSI reclaims, with the strike.",
      render: () => <AtSupport body={sup?.body ?? ""} onChart={onChart} /> },
    // ── WEEKLY VALUE — names at their WEEKLY volume-profile POC/VWAP/VAL (Robinhood data,
    //    matches the chart). Top 10, fresh reclaims first (prior day's first close above). ──
    { id: "sec-weekly-vp", group: "Buy the dip", time: "PREMKT", title: "Weekly Value", present: !!wvp,
      wait: "The weekly-value scan runs premarket (analytics/weekly_vp_scan.py).",
      render: () => <WeeklyValue body={wvp?.body ?? ""} onChart={onChart} /> },
    // ── MOMENTUM — the swing finder's breakout/structure buckets only (the oversold ones
    //    moved to the support board) + premarket gaps. ──
    { id: "sec-swing", group: "Momentum", time: "10:30·15:00", title: "Momentum / Swing", present: !!sw,
      wait: "The swing finder runs midday + before the close.",
      render: () => <SwingSetups body={sw?.body ?? ""} onChart={onChart} exclude={["rsi30", "sma200", "ma_hold"]} /> },
    { id: "sec-gap", group: "Momentum", time: "PREMKT", title: "Gap setups", present: !!gap,
      wait: "The gap scan runs premarket (analytics/gap_scanner.py).",
      render: () => <GapSetups body={gap?.body ?? ""} onChart={onChart} /> },
    // ── BREAKOUTS — Zanger-style momentum patterns (cup&handle, flat base, ascending
    //    triangle, bull flag, TBA/horizontal break, descending-trendline break). TBA = buy
    //    trigger, max stop = invalidation. Nightly batch after the close (patterns/run.py). ──
    { id: "sec-breakouts", group: "Momentum", time: "EOD", title: "Breakouts", present: !!bo,
      wait: "The breakout scanner runs nightly after the close (patterns/run.py --universe --publish).",
      render: () => <Breakouts body={bo?.body ?? ""} onChart={onChart} /> },
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
          {sections.flatMap((s, i) => {
            const showGroup = i === 0 || sections[i - 1].group !== s.group;
            const out = [];
            if (showGroup)
              out.push(<div key={`g-${s.group}`} className="mt-2.5 mb-1 px-2.5 text-[9px] font-bold uppercase tracking-wider text-text-faint first:mt-0">{s.group}</div>);
            out.push(
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
              </button>,
            );
            return out;
          })}
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
        {sections.map((s, i) => {
          const open = openSecs.has(s.id);
          const showGroup = i === 0 || sections[i - 1].group !== s.group;
          return (
            <section key={s.id} id={s.id} className="scroll-mt-4">
              {/* group label sits INSIDE the section (above the header) so it can't overlap it */}
              {showGroup && <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-accent/80">{s.group}</div>}
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
