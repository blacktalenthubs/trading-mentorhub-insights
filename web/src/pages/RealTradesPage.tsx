/** Trades — Alert Outcome Analytics & Decision Quality.
 *
 *  Sections:
 *    1. Performance stats (P&L, win rate, expectancy, avg win/loss)
 *    2. Equity curve
 *    3. Decision quality (took vs skipped outcomes)
 *    4. Session browser (pick a date, see all alerts + outcomes)
 *    5. Alert history table (expandable rows)
 */

import { useState } from "react";
import {
  useAlertsHistory, useAlertsToday, useRealTradeStats,
  useRealTradeEquityCurve, useAlertSessionDates, useAlertsForDate,
} from "../api/hooks";
import EquityCurve from "../components/EquityCurve";
import type { Alert } from "../types";
import {
  TrendingUp, TrendingDown, Target, ShieldAlert, BarChart3,
  Calendar, ChevronDown, ChevronRight, Download, FileText,
} from "lucide-react";

/* ── helpers ──────────────────────────────────────────────────────── */

function fmt(v: number | null | undefined, d = 2): string {
  if (v == null) return "—";
  return v.toFixed(d);
}

/* ── Stat card ────────────────────────────────────────────────────── */

function Stat({ label, value, sub, color, icon }: {
  label: string; value: string; sub?: string; color?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 flex flex-col">
      <div className="flex items-center gap-1.5 mb-1">
        {icon}
        <span className="text-[10px] text-text-faint uppercase tracking-wider font-medium">{label}</span>
      </div>
      <span className={`font-mono text-xl font-bold ${color || "text-text-primary"}`}>{value}</span>
      {sub && <span className="text-[10px] text-text-faint mt-0.5">{sub}</span>}
    </div>
  );
}

/* ── Alert row (expandable) ───────────────────────────────────────── */

function AlertHistoryRow({ alert: a }: { alert: Alert }) {
  const [expanded, setExpanded] = useState(false);
  const time = new Date(a.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
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
          <div className="py-12 text-center text-text-faint text-sm">No alerts for {selectedDate}</div>
        ) : (
          <div className="py-12 text-center text-text-faint text-sm">Select a session date</div>
        )}
      </div>
    </div>
  );
}

/* ── Main Trades Page ─────────────────────────────────────────────── */

export default function RealTradesPage() {
  const { data: stats } = useRealTradeStats();
  const { data: equityCurve } = useRealTradeEquityCurve();
  const { data: todayAlerts } = useAlertsToday();
  const { data: allAlerts } = useAlertsHistory(30);

  const alertsForQuality = todayAlerts || [];

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-[1400px] mx-auto flex flex-col gap-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-text-primary">Trade Analytics</h1>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (!allAlerts || allAlerts.length === 0) return;
                const header = "Date,Time,Symbol,Direction,Type,Price,Entry,Stop,T1,T2,Confidence,Action,Message\n";
                const rows = allAlerts.map((a) =>
                  `${a.session_date},${a.created_at},${a.symbol},${a.direction},${a.alert_type},${a.price},${a.entry ?? ""},${a.stop ?? ""},${a.target_1 ?? ""},${a.target_2 ?? ""},${a.confidence ?? ""},${a.user_action ?? ""},${(a.message || "").replace(/,/g, ";")}`
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

        {/* Performance Stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <Stat
              label="Total P&L"
              value={`$${stats.total_pnl.toFixed(2)}`}
              color={stats.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}
              icon={stats.total_pnl >= 0 ? <TrendingUp className="h-3 w-3 text-bullish-text" /> : <TrendingDown className="h-3 w-3 text-bearish-text" />}
            />
            <Stat label="Win Rate" value={`${stats.win_rate}%`} sub={`${stats.win_count}W / ${stats.loss_count}L`}
              icon={<Target className="h-3 w-3 text-bullish-text" />} />
            <Stat label="Total Trades" value={`${stats.total_trades}`} />
            <Stat
              label="Expectancy"
              value={`$${stats.expectancy.toFixed(2)}`}
              color={stats.expectancy >= 0 ? "text-bullish-text" : "text-bearish-text"}
            />
            <Stat label="Avg Win" value={`$${stats.avg_win.toFixed(2)}`} color="text-bullish-text" />
            <Stat label="Avg Loss" value={`$${stats.avg_loss.toFixed(2)}`} color="text-bearish-text"
              icon={<ShieldAlert className="h-3 w-3 text-bearish-text" />} />
          </div>
        )}

        {/* Equity Curve + Decision Quality (side by side) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Equity Curve */}
          {equityCurve && equityCurve.length > 1 && (
            <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-bullish-text" />
                Equity Curve
              </h3>
              <EquityCurve data={equityCurve} height={200} />
            </div>
          )}

          {/* Decision Quality */}
          <DecisionQuality alerts={alertsForQuality} />
        </div>

        {/* Session Browser */}
        <SessionBrowser />

      </div>
    </div>
  );
}
