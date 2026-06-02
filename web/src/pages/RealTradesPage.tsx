/** Trades — Manual exit-price collection + per-alert-type performance.
 *
 *  Redesigned 2026-05-28: dropped synthetic $45k/trade P&L, fake equity
 *  curve, retired ai_* patterns. Page is now a real-data feedback loop:
 *  user enters the actual exit price on every Took alert; R-multiple is
 *  computed; performance rolls up per alert_type from the live spec-58
 *  catalog. Over time this surfaces which patterns actually work.
 */

import { useState } from "react";
import {
  useAlertsHistory, useAlertsToday,
  useAlertSessionDates, useAlertsForDate,
  useAlertTypePerformance, useSetAlertExit,
} from "../api/hooks";
import EODReportPage from "./EODReportPage";
import TradeReviewPage from "./TradeReviewPage";
import WeeklyReport from "../components/WeeklyReport";
import { SkeletonRow } from "../components/ui/Skeleton";
import EmptyState from "../components/ui/EmptyState";
import type { Alert } from "../types";
import {
  BarChart3, Calendar, ChevronDown, ChevronRight, Download, FileText, Check,
} from "lucide-react";

type PerfTab = "by-pattern" | "weekly" | "today-eod" | "by-symbol" | "sessions";

/* ── helpers ──────────────────────────────────────────────────────── */

function fmt(v: number | null | undefined, d = 2): string {
  if (v == null) return "—";
  return v.toFixed(d);
}

/* ── Alert row (expandable) ───────────────────────────────────────── */

function AlertHistoryRow({ alert: a }: { alert: Alert }) {
  const [expanded, setExpanded] = useState(false);
  const time = new Date(a.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", timeZone: "America/Chicago" });
  const rr = a.entry && a.stop && a.target_1
    ? ((a.target_1 - a.entry) / Math.abs(a.entry - a.stop)).toFixed(1)
    : null;

  const dirBg = a.direction === "BUY" ? "bg-bullish/10 text-bullish-text" :
    a.direction === "SHORT" ? "bg-bearish/10 text-bearish-text" :
    a.direction === "SELL" ? "bg-warning/10 text-warning-text" : "bg-surface-3 text-text-muted";

  const actionBadge = a.user_action === "took"
    ? <span className="text-[10px] font-bold text-bullish-text bg-bullish/10 px-2 py-0.5 rounded">TOOK</span>
    : a.user_action === "skipped"
    ? <span className="text-[10px] font-bold text-text-faint bg-surface-3 px-2 py-0.5 rounded">SKIPPED</span>
    : <span className="text-[10px] text-text-faint">—</span>;

  return (
    <div className="border-b border-border-subtle/30 hover:bg-surface-2/20 transition-colors">
      <div
        className="flex items-center gap-3 px-4 py-2.5 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronDown className="h-3 w-3 text-text-faint shrink-0" /> : <ChevronRight className="h-3 w-3 text-text-faint shrink-0" />}
        <span className="font-mono text-xs text-text-faint w-14 shrink-0">{time}</span>
        <span className="font-bold text-sm text-text-primary w-20 shrink-0">{a.symbol}</span>
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${dirBg}`}>{a.direction}</span>
        <span className="text-xs text-text-muted flex-1 truncate">{a.alert_type.replace(/_/g, " ")}</span>
        <span className="font-mono text-sm text-text-primary shrink-0 w-20 text-right">${fmt(a.price)}</span>
        <div className="w-20 text-right shrink-0">{actionBadge}</div>
      </div>

      {expanded && (
        <div className="px-4 pb-3 pl-10 space-y-2">
          {/* Levels */}
          {a.entry != null && (
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
              <span className="text-text-muted">Entry: <span className="font-mono text-text-primary">${fmt(a.entry)}</span></span>
              {a.stop != null && <span className="text-text-muted">Stop: <span className="font-mono text-bearish-text">${fmt(a.stop)}</span></span>}
              {a.target_1 != null && <span className="text-text-muted">T1: <span className="font-mono text-bullish-text">${fmt(a.target_1)}</span></span>}
              {a.target_2 != null && <span className="text-text-muted">T2: <span className="font-mono text-bullish-text">${fmt(a.target_2)}</span></span>}
              {rr && <span className="text-text-muted">R:R: <span className="font-mono text-text-primary">1:{rr}</span></span>}
            </div>
          )}
          {/* Exit-price input — only meaningful when user actually entered the trade. */}
          {a.user_action === "took" && a.entry != null && a.stop != null && (
            <ExitPriceInput alert={a} />
          )}
          {a.message && (
            <p className="text-xs text-text-secondary leading-relaxed">{a.message}</p>
          )}
          <div className="text-[10px] text-text-faint">
            {a.confidence && <span>{a.confidence} confidence · </span>}
            {a.session_date}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Exit-price input — manual real-trade close ──────────────────── */

function ExitPriceInput({ alert: a }: { alert: Alert }) {
  const [value, setValue] = useState<string>(a.exit_price != null ? String(a.exit_price) : "");
  const setExit = useSetAlertExit();

  const saved = a.exit_price != null;
  const r = a.r_multiple;
  const rColor = r == null ? "text-text-faint" : r > 0 ? "text-bullish-text" : "text-bearish-text";

  function save() {
    const trimmed = value.trim();
    const parsed = trimmed === "" ? null : Number(trimmed);
    if (parsed != null && (isNaN(parsed) || parsed <= 0)) return;
    setExit.mutate({ alertId: a.id, exitPrice: parsed });
  }

  return (
    <div className="flex items-center gap-2 bg-surface-0 border border-border-subtle/50 rounded px-2.5 py-1.5">
      <span className="text-[10px] uppercase tracking-wider text-text-faint shrink-0">Exit</span>
      <span className="text-text-faint text-xs">$</span>
      <input
        type="number"
        step="0.01"
        inputMode="decimal"
        placeholder={a.entry != null ? fmt(a.entry) : ""}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
        className="font-mono text-xs bg-transparent text-text-primary w-20 focus:outline-none placeholder:text-text-faint/40"
      />
      {saved && <Check className="h-3 w-3 text-bullish-text shrink-0" />}
      {r != null && (
        <span className={`font-mono text-xs font-semibold ${rColor}`}>
          {r > 0 ? "+" : ""}{r.toFixed(2)}R
        </span>
      )}
      {setExit.isPending && <span className="text-[10px] text-text-faint">saving…</span>}
    </div>
  );
}

/* ── Decision Quality Card ────────────────────────────────────────── */

function DecisionQuality({ alerts }: { alerts: Alert[] }) {
  const took = alerts.filter((a) => a.user_action === "took");
  const skipped = alerts.filter((a) => a.user_action === "skipped");
  const pending = alerts.filter((a) => !a.user_action && (a.direction === "BUY" || a.direction === "SHORT"));

  // Count outcomes by checking if target/stop alerts fired for the same symbol+session
  const targetSymbols = new Set(alerts.filter((a) => a.alert_type.includes("target")).map((a) => a.symbol));
  const stopSymbols = new Set(alerts.filter((a) => a.alert_type.includes("stop")).map((a) => a.symbol));

  const tookWins = took.filter((a) => targetSymbols.has(a.symbol)).length;
  const tookLosses = took.filter((a) => stopSymbols.has(a.symbol)).length;
  const skippedWouldWin = skipped.filter((a) => targetSymbols.has(a.symbol)).length;

  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
      <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-accent" />
        Decision Quality
      </h3>

      <div className="grid grid-cols-3 gap-4">
        {/* Took */}
        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Alerts Took</div>
          <div className="text-2xl font-mono font-bold text-text-primary">{took.length}</div>
          {took.length > 0 && (
            <div className="flex gap-3 mt-2 text-xs">
              <span className="text-bullish-text">{tookWins} won</span>
              <span className="text-bearish-text">{tookLosses} lost</span>
              <span className="text-text-faint">{took.length - tookWins - tookLosses} open</span>
            </div>
          )}
        </div>

        {/* Skipped */}
        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Alerts Skipped</div>
          <div className="text-2xl font-mono font-bold text-text-primary">{skipped.length}</div>
          {skipped.length > 0 && skippedWouldWin > 0 && (
            <div className="mt-2 text-xs text-warning-text">
              {skippedWouldWin} would have won
            </div>
          )}
        </div>

        {/* Pending */}
        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">No Action</div>
          <div className="text-2xl font-mono font-bold text-text-faint">{pending.length}</div>
          {pending.length > 0 && (
            <div className="mt-2 text-xs text-text-faint">Awaiting decision</div>
          )}
        </div>
      </div>

      {/* Edge insight */}
      {took.length >= 3 && (
        <div className="mt-4 pt-3 border-t border-border-subtle/50 text-xs text-text-secondary">
          {tookWins > tookLosses ? (
            <span className="text-bullish-text">Your filtering is working — {((tookWins / Math.max(tookWins + tookLosses, 1)) * 100).toFixed(0)}% win rate on trades you took.</span>
          ) : tookWins < tookLosses ? (
            <span className="text-warning-text">Review your entries — more stops than targets on trades you took. Consider tightening criteria.</span>
          ) : (
            <span>Balanced results so far. Keep building the sample size.</span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Session Browser ──────────────────────────────────────────────── */

function SessionBrowser() {
  const { data: dates } = useAlertSessionDates();
  const [selectedDate, setSelectedDate] = useState("");
  const { data: dateAlerts } = useAlertsForDate(selectedDate);

  // Default to most recent date
  if (dates && dates.length > 0 && !selectedDate) {
    setSelectedDate(dates[0]);
  }

  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl flex flex-col overflow-hidden">
      {/* Header with date picker */}
      <div className="px-5 py-3.5 border-b border-border-subtle flex items-center justify-between bg-surface-2/20">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Calendar className="h-4 w-4 text-text-muted" />
          Session History
        </h3>
        <div className="flex items-center gap-2">
          {dates && (
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-surface-3 border border-border-subtle rounded-md px-2.5 py-1 text-xs text-text-primary font-mono focus:border-accent focus:outline-none"
            >
              {dates.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Alert list for selected date */}
      <div className="flex-1 overflow-auto max-h-[400px]">
        {dateAlerts && dateAlerts.length > 0 ? (
          <div>
            {/* Column headers */}
            <div className="flex items-center gap-3 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint font-medium border-b border-border-subtle/50 bg-surface-0/50 sticky top-0">
              <span className="w-3" />
              <span className="w-14">Time</span>
              <span className="w-20">Symbol</span>
              <span className="w-14">Dir</span>
              <span className="flex-1">Type</span>
              <span className="w-20 text-right">Price</span>
              <span className="w-20 text-right">Action</span>
            </div>
            {dateAlerts.map((a) => <AlertHistoryRow key={a.id} alert={a} />)}
          </div>
        ) : selectedDate ? (
          <EmptyState
            size="sm"
            title={`No alerts on ${selectedDate}`}
            hint="The scanner didn't fire any alerts that day. Try a different date or check your watchlist."
            primary={{ label: "Edit watchlist", to: "/watchlist" }}
          />
        ) : (
          <EmptyState
            size="sm"
            icon={Calendar}
            title="Pick a session date"
            hint="Choose a date from the selector above to load alerts."
          />
        )}
      </div>
    </div>
  );
}

/* ── Performance by Alert Type — real data only ──────────────────── */

function WinRateBar({ rate, height = "h-2" }: { rate: number; height?: string }) {
  const color = rate >= 60 ? "bg-bullish" : rate >= 45 ? "bg-warning" : "bg-bearish";
  return (
    <div className={`w-full ${height} bg-surface-3 rounded-full overflow-hidden`}>
      <div className={`${height} ${color} rounded-full transition-all`} style={{ width: `${Math.min(rate, 100)}%` }} />
    </div>
  );
}

function AlertTypePerformanceSection() {
  const { data, isLoading } = useAlertTypePerformance();

  if (isLoading) {
    return (
      <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 space-y-2" aria-busy="true">
        <SkeletonRow count={6} h={32} />
      </div>
    );
  }

  const items = data?.items ?? [];
  const tookSomething = items.some((i) => i.took > 0);

  return (
    <div>
      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3 flex items-center gap-2">
        <BarChart3 className="h-3.5 w-3.5 text-accent" />
        Performance by Alert Type
      </h3>
      <p className="text-xs text-text-faint mb-3">
        Real R-multiple from your recorded exit prices. Patterns you haven't Took yet won't appear.
        Enter the exit price under any Took alert below to add data.
      </p>

      {!tookSomething ? (
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-6 text-center">
          <p className="text-sm text-text-secondary">No Took alerts yet.</p>
          <p className="text-xs text-text-faint mt-1">
            When a real alert fires and you take the trade, mark it Took and come back here to record the exit.
          </p>
        </div>
      ) : (
        <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-text-faint font-medium border-b border-border-subtle/50 bg-surface-2/30">
            <span className="col-span-5">Alert Type</span>
            <span className="col-span-1 text-right">Took</span>
            <span className="col-span-1 text-right">Closed</span>
            <span className="col-span-2 text-right">Win Rate</span>
            <span className="col-span-1 text-right">Avg R</span>
            <span className="col-span-2 text-right">Best / Worst</span>
          </div>
          {items.map((it) => {
            const wr = it.win_rate;
            const wrColor = wr == null ? "text-text-faint"
              : wr >= 60 ? "text-bullish-text" : wr >= 45 ? "text-warning-text" : "text-bearish-text";
            const avgR = it.avg_r;
            const avgRColor = avgR == null ? "text-text-faint"
              : avgR > 0 ? "text-bullish-text" : "text-bearish-text";
            return (
              <div key={it.alert_type} className="grid grid-cols-12 gap-2 px-4 py-2 border-b border-border-subtle/30 last:border-b-0 items-center text-xs">
                <span
                  className="col-span-5 text-text-primary truncate cursor-help"
                  title={it.description || it.label}
                >
                  {it.label}
                </span>
                <span className="col-span-1 text-right font-mono text-text-secondary">{it.took}</span>
                <span className="col-span-1 text-right font-mono text-text-secondary">{it.with_exit}</span>
                <div className="col-span-2 flex items-center justify-end gap-2">
                  <div className="w-12 hidden md:block">
                    {wr != null && <WinRateBar rate={wr} height="h-1.5" />}
                  </div>
                  <span className={`font-mono font-semibold ${wrColor}`}>
                    {wr == null ? "—" : `${wr}%`}
                  </span>
                </div>
                <span className={`col-span-1 text-right font-mono font-semibold ${avgRColor}`}>
                  {avgR == null ? "—" : `${avgR > 0 ? "+" : ""}${avgR}R`}
                </span>
                <span className="col-span-2 text-right font-mono text-[11px] text-text-muted">
                  {it.best_r == null ? "—" : (
                    <>
                      <span className="text-bullish-text">{it.best_r > 0 ? "+" : ""}{it.best_r}</span>
                      {" / "}
                      <span className="text-bearish-text">{it.worst_r}</span>
                    </>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


/* ── Main Trades Page ─────────────────────────────────────────────── */

const PERF_TABS: { id: PerfTab; label: string }[] = [
  { id: "by-pattern", label: "By Pattern" },
  { id: "weekly",     label: "Weekly" },
  { id: "today-eod",  label: "Today's EOD" },
  { id: "by-symbol",  label: "By Symbol" },
  { id: "sessions",   label: "Sessions" },
];

export default function RealTradesPage() {
  const [activeTab, setActiveTab] = useState<PerfTab>(() => {
    if (typeof window === "undefined") return "by-pattern";
    return (localStorage.getItem("perf_active_tab") as PerfTab) || "by-pattern";
  });
  function pickTab(t: PerfTab) {
    setActiveTab(t);
    try { localStorage.setItem("perf_active_tab", t); } catch {}
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-[1400px] mx-auto flex flex-col gap-6">

        {/* Header + Tab bar */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-6 flex-wrap">
            <h1 className="text-xl font-bold text-text-primary">Performance</h1>
            <div className="flex bg-surface-2 rounded-lg p-0.5 flex-wrap">
              {PERF_TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => pickTab(t.id)}
                  className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                    activeTab === t.id
                      ? "bg-surface-4 text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 2026-06-01 — Performance analytics unlocked for everyone (public
            launch). Previous tier gate restored under TierGate require="pro". */}
        {activeTab === "by-pattern" && <DayTradesContent />}
        {activeTab === "weekly"     && <WeeklyReport />}
        {activeTab === "today-eod"  && <div className="-mx-5 -mb-5"><EODReportPage /></div>}
        {activeTab === "by-symbol"  && <div className="-mx-5 -mb-5"><TradeReviewPage /></div>}
        {activeTab === "sessions"   && <SessionBrowser />}
      </div>
    </div>
  );
}


/* ── Day Trades Tab ──────────────────────────────────────────────── */

function DayTradesContent() {
  const { data: todayAlerts } = useAlertsToday();
  const { data: allAlerts } = useAlertsHistory(30);

  const alertsForQuality = todayAlerts || [];

  return (
    <>
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-faint max-w-xl">
          Mark Took / Skipped on real alerts, then enter the actual exit price when you close.
          Performance below is real R-multiple — no synthetic P&amp;L, no retired patterns.
        </p>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              if (!allAlerts || allAlerts.length === 0) return;
              const header = "Date,Time,Symbol,Direction,Type,Price,Entry,Stop,Exit,R,Action,Message\n";
              const rows = allAlerts.map((a) =>
                `${a.session_date},${a.created_at},${a.symbol},${a.direction},${a.alert_type},${a.price},${a.entry ?? ""},${a.stop ?? ""},${a.exit_price ?? ""},${a.r_multiple ?? ""},${a.user_action ?? ""},${(a.message || "").replace(/,/g, ";")}`
              ).join("\n");
              const blob = new Blob([header + rows], { type: "text/csv" });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = `tradesignal_history_${new Date().toISOString().slice(0, 10)}.csv`;
              link.click();
              URL.revokeObjectURL(url);
            }}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary bg-surface-2 hover:bg-surface-3 border border-border-subtle px-3 py-1.5 rounded-lg transition-colors"
          >
            <Download className="h-3 w-3" /> Export CSV
          </button>
          <a
            href="/api/v1/alerts/pdf"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary bg-surface-2 hover:bg-surface-3 border border-border-subtle px-3 py-1.5 rounded-lg transition-colors"
          >
            <FileText className="h-3 w-3" /> PDF Report
          </a>
        </div>
      </div>

      {/* Decision Quality */}
      <DecisionQuality alerts={alertsForQuality} />

      {/* Per-alert-type performance — real R-multiple from recorded exits */}
      <AlertTypePerformanceSection />
    </>
  );
}
