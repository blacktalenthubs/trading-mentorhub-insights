/** TodayPage — the redesigned authenticated home (Sub-spec J), on live data.
 *  Two tabs:
 *   • Signals  — the quick entry/exit feed (unchanged).
 *   • Briefing — the AI agent's READ on each alert (the narrative that goes to
 *     Telegram), now surfaced in the app, collapsible per alert. The default
 *     place busy users come to see the "why", not just the numbers.
 *  Its own scroll root (AppLayout <main> is overflow-hidden — see
 *  feedback_page_scroll_container).
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useSpyLiveRegime, useBtcLiveRegime, useMarketReports, useReportDates, useBottomWatch, type BottomWatchItem } from "../api/hooks";
import type { SpyRegimeSnapshot } from "../api/hooks";
import GapGoQueue from "../components/GapGoQueue";

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
      {/* Non-actionable context — collapsed to thin count chips (not big grids).
          Extended = wait for a pullback; Rolling off = lost the 20, not an entry. */}
      {(extended.length > 0 || rolling.length > 0) && (
        <div className="flex flex-wrap items-center gap-2 pt-0.5 text-[11px]">
          {extended.length > 0 && (
            <span className="rounded-md bg-surface-2 px-2.5 py-1 text-text-faint">
              <b className="text-text-muted">Extended · {extended.length}</b> — strong trend, wait for a pullback to the 20
            </span>
          )}
          {rolling.length > 0 && (
            <span className="rounded-md bg-surface-2 px-2.5 py-1 text-text-faint opacity-80">
              <b className="text-text-muted">Rolling off · {rolling.length}</b> — lost the 20, not an entry
            </span>
          )}
        </div>
      )}
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
  return (
    <div className="rounded-xl border border-accent/25 bg-accent/5 p-3">
      <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-accent">📡 Moving premarket · {sigs.length} at a level</div>
      <div className="flex flex-wrap gap-1.5">
        {sigs.map((s) => (
          <button
            key={s.symbol + s.alert_type}
            onClick={() => onChart(s.symbol)}
            title={`${PM_LABEL[s.alert_type] ?? s.alert_type} · entry $${s.entry} · stop $${s.stop}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-surface-1 px-2.5 py-1 text-[11px] transition-colors hover:border-accent"
          >
            <b className="text-text-primary">{s.symbol}</b>
            <span className={s.gap_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}>{s.gap_pct >= 0 ? "+" : ""}{s.gap_pct}%</span>
            <span className="text-text-faint">{PM_LABEL[s.alert_type] ?? s.alert_type}</span>
          </button>
        ))}
      </div>
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
  const ps = data?.premarket_signals ?? null;
  // Timeline rail: which section is active (scroll target). No tab state — every
  // report renders in one scroll, in the order it drops through the day.
  const [activeSec, setActiveSec] = useState<string>("sec-focus");
  const rawText = (b?: string | null) => (b ? b.replace(/<\/?(pre|b|i|code|strong|em)>/gi, "") : "");

  if (isLoading) {
    return <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">Loading reports…</div>;
  }

  const sections = [
    { id: "sec-premarket", time: "4:30a", title: "Premarket brief", present: !!pre,
      wait: "Drops pre-open (~8:30 AM ET).", render: () => <TextReport text={rawText(pre?.body)} /> },
    { id: "sec-focus", time: "8:55a", title: "Today's Focus", present: !!mf || !!ps,
      wait: "Leaders Near a Buy Point drop pre-open (~8:45 AM ET).",
      render: () => (
        <div className="space-y-4">
          {/* premarket movers merged IN — the live "what's at a level" read, atop the plan */}
          <PremarketStrip body={ps?.body} onChart={onChart} />
          {mf
            ? <FocusPicks body={mf.body} onChart={onChart} />
            : <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">Curated focus picks drop ~8:55 ET.</div>}
        </div>
      ) },
    { id: "sec-trend", time: "ALL·DAY", title: "Trend setups", present: !!ts,
      wait: "Generated after the close (~4:15 PM ET).", render: () => <TrendSetups body={ts!.body} onChart={onChart} /> },
    { id: "sec-bottom", time: "ALL·DAY", title: "Bottom watch", present: true,
      wait: "", render: () => <BottomWatchBoard onChart={onChart} /> },
    { id: "sec-eod", time: "4:10p", title: "EOD recap", present: !!eod,
      wait: "Generated after the close (~4:05 PM ET).", render: () => <TextReport text={rawText(eod?.body)} /> },
  ];
  const jump = (id: string) => {
    setActiveSec(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="grid grid-cols-1 gap-5 md:grid-cols-[190px_1fr]">
      {/* Timeline rail — the day's reports in order; click to jump. */}
      <nav className="hidden self-start md:sticky md:top-2 md:block">
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
        {reportDates.length > 0 && (
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            title="Review a past session"
            className="mt-3 w-full rounded-lg border border-border-subtle bg-surface-2 px-2 py-1.5 text-[11px] text-text-secondary"
          >
            <option value="">Latest</option>
            {reportDates.map((d) => (
              <option key={d} value={d}>{fmtDate(d)}</option>
            ))}
          </select>
        )}
      </nav>

      {/* Content — every report section in one scroll. */}
      <div className="min-w-0 space-y-8">
        {/* Gap-and-Go Queue — top-3 quality gappers (self-hides when empty). */}
        <GapGoQueue onChart={onChart} />
        {sections.map((s) => (
          <section key={s.id} id={s.id} className="scroll-mt-4">
            <div className="mb-2.5 flex items-baseline gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wide text-text-faint">{s.time}</span>
              <h2 className="text-[13px] font-bold text-text-primary">{s.title}</h2>
            </div>
            {s.present ? s.render() : (
              <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">{s.wait}</div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

/** Raw-text report card (premarket brief / EOD recap) — strips Telegram HTML tags. */
function TextReport({ text }: { text: string }) {
  if (!text.trim()) return null;
  return (
    <div className="max-w-3xl rounded-xl border border-border-subtle bg-surface-1 p-4">
      <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-text-secondary">{text}</pre>
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
