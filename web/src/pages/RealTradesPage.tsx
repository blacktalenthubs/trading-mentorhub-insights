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
  useSpyRegime, useSwingCategories, useActiveSwingTrades,
  useSwingTradesHistory, useTriggerSwingScan, usePerformanceBreakdown,
} from "../api/hooks";
import EquityCurve from "../components/EquityCurve";
import type { Alert, PerformanceBreakdown } from "../types";
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

/* ── Performance Breakdown ───────────────────────────────────────── */

function WinRateBar({ rate, height = "h-2" }: { rate: number; height?: string }) {
  const color = rate >= 60 ? "bg-bullish" : rate >= 45 ? "bg-warning" : "bg-bearish";
  return (
    <div className={`w-full ${height} bg-surface-3 rounded-full overflow-hidden`}>
      <div className={`${height} ${color} rounded-full transition-all`} style={{ width: `${Math.min(rate, 100)}%` }} />
    </div>
  );
}

function PerformanceBreakdownSection({ data }: { data: PerformanceBreakdown }) {
  const topPatterns = data.by_pattern.filter((p) => p.trades >= 3).slice(0, 5);
  const topSymbols = data.by_symbol.slice(0, 5);
  const hoursSorted = [...data.by_hour].sort((a, b) => parseInt(a.hour) - parseInt(b.hour));
  const daysOrder = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
  const daysSorted = daysOrder
    .map((d) => data.by_day.find((x) => x.day === d))
    .filter(Boolean) as typeof data.by_day;

  const bestHour = data.by_hour.length > 0
    ? data.by_hour.reduce((best, h) => h.win_rate > best.win_rate && h.trades >= 2 ? h : best, data.by_hour[0])
    : null;

  const isEmpty = data.by_pattern.length === 0 && data.by_symbol.length === 0;
  if (isEmpty) return null;

  return (
    <div>
      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3 flex items-center gap-2">
        <BarChart3 className="h-3.5 w-3.5 text-accent" />
        Performance Breakdown
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">

        {/* Best Patterns */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <div className="text-[10px] text-text-faint uppercase tracking-wider font-medium mb-3">Best Patterns</div>
          {topPatterns.length > 0 ? (
            <div className="space-y-2.5">
              {topPatterns.map((p) => (
                <div key={p.pattern}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-text-primary font-medium truncate mr-2">{p.label}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] text-text-faint">{p.trades} trades</span>
                      <span className={`text-xs font-mono font-bold ${p.win_rate >= 60 ? "text-bullish-text" : p.win_rate >= 45 ? "text-warning-text" : "text-bearish-text"}`}>
                        {p.win_rate}%
                      </span>
                    </div>
                  </div>
                  <WinRateBar rate={p.win_rate} />
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-faint text-center py-4">Need 3+ trades per pattern</p>
          )}
        </div>

        {/* Best Time */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[10px] text-text-faint uppercase tracking-wider font-medium">Best Time</div>
            {bestHour && bestHour.trades >= 2 && (
              <span className="text-[10px] text-accent font-medium">Golden hour: {bestHour.label}</span>
            )}
          </div>
          {hoursSorted.length > 0 ? (
            <div className="space-y-2">
              {hoursSorted.map((h) => (
                <div key={h.hour} className="flex items-center gap-2">
                  <span className="text-[10px] font-mono text-text-muted w-10 shrink-0">{h.label}</span>
                  <div className="flex-1">
                    <WinRateBar rate={h.win_rate} height="h-1.5" />
                  </div>
                  <span className={`text-[10px] font-mono w-10 text-right shrink-0 ${h.win_rate >= 60 ? "text-bullish-text" : h.win_rate >= 45 ? "text-warning-text" : "text-bearish-text"}`}>
                    {h.win_rate}%
                  </span>
                  <span className="text-[10px] text-text-faint w-6 text-right shrink-0">{h.trades}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-faint text-center py-4">No time data yet</p>
          )}
        </div>

        {/* By Symbol */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <div className="text-[10px] text-text-faint uppercase tracking-wider font-medium mb-3">Top Symbols by P&L</div>
          {topSymbols.length > 0 ? (
            <div className="space-y-2">
              {topSymbols.map((s) => (
                <div key={s.symbol} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-text-primary w-14">{s.symbol}</span>
                    <span className="text-[10px] text-text-faint">{s.trades} trades</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-[10px] font-mono ${s.win_rate >= 60 ? "text-bullish-text" : s.win_rate >= 45 ? "text-warning-text" : "text-bearish-text"}`}>
                      {s.win_rate}% WR
                    </span>
                    <span className={`text-xs font-mono font-bold ${s.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      {s.total_pnl >= 0 ? "+" : ""}${s.total_pnl.toFixed(0)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-text-faint text-center py-4">No closed trades yet</p>
          )}
        </div>

        {/* By Day of Week */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <div className="text-[10px] text-text-faint uppercase tracking-wider font-medium mb-3">By Day of Week</div>
          {daysSorted.length > 0 ? (
            <div className="flex items-end gap-2 h-24">
              {daysSorted.map((d) => {
                const barH = Math.max(d.win_rate * 0.8, 8);
                const color = d.win_rate >= 60 ? "bg-bullish" : d.win_rate >= 45 ? "bg-warning" : "bg-bearish";
                return (
                  <div key={d.day} className="flex-1 flex flex-col items-center gap-1">
                    <span className={`text-[10px] font-mono font-bold ${d.win_rate >= 60 ? "text-bullish-text" : d.win_rate >= 45 ? "text-warning-text" : "text-bearish-text"}`}>
                      {d.win_rate}%
                    </span>
                    <div className={`w-full rounded-t ${color}`} style={{ height: `${barH}%` }} />
                    <span className="text-[10px] text-text-faint">{d.day.slice(0, 3)}</span>
                    <span className="text-[9px] text-text-faint">{d.trades}t</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-text-faint text-center py-4">No day data yet</p>
          )}
        </div>

      </div>
    </div>
  );
}

/* ── Main Trades Page ─────────────────────────────────────────────── */

export default function RealTradesPage() {
  const [activeTab, setActiveTab] = useState<"day" | "swing">("day");

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-[1400px] mx-auto flex flex-col gap-6">

        {/* Header + Tab bar */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-bold text-text-primary">Trades</h1>
            <div className="flex bg-surface-2 rounded-lg p-0.5">
              <button
                onClick={() => setActiveTab("day")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  activeTab === "day"
                    ? "bg-surface-4 text-text-primary shadow-sm"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Day Trades
              </button>
              <button
                onClick={() => setActiveTab("swing")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                  activeTab === "swing"
                    ? "bg-surface-4 text-text-primary shadow-sm"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Swing Trades
              </button>
            </div>
          </div>
        </div>

        {activeTab === "day" ? <DayTradesContent /> : <SwingTradesContent />}
      </div>
    </div>
  );
}


/* ── Day Trades Tab ──────────────────────────────────────────────── */

function DayTradesContent() {
  const { data: stats } = useRealTradeStats();
  const { data: equityCurve } = useRealTradeEquityCurve();
  const { data: todayAlerts } = useAlertsToday();
  const { data: allAlerts } = useAlertsHistory(30);
  const { data: breakdown } = usePerformanceBreakdown();

  const alertsForQuality = todayAlerts || [];

  return (
    <>
        <div className="flex items-center justify-between">
          <div /> {/* spacer */}
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

        {/* Performance Breakdown */}
        {breakdown && <PerformanceBreakdownSection data={breakdown} />}

        {/* Session Browser */}
        <SessionBrowser />
    </>
  );
}


/* ── Swing Trades Tab ────────────────────────────────────────────── */

function SwingTradesContent() {
  const { data: regime } = useSpyRegime();
  const { data: categories } = useSwingCategories();
  const { data: activeTrades } = useActiveSwingTrades();
  const { data: history } = useSwingTradesHistory();
  const triggerScan = useTriggerSwingScan();
  const [expandedSwing, setExpandedSwing] = useState<number | null>(null);

  return (
    <>
      {/* SPY Regime */}
      {regime && (
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 flex items-center gap-4">
          <span className={`text-xs font-bold px-2.5 py-1 rounded ${
            regime.regime_bullish
              ? "bg-bullish/10 text-bullish-text border border-bullish/20"
              : "bg-bearish/10 text-bearish-text border border-bearish/20"
          }`}>
            SPY {regime.regime_bullish ? "BULLISH" : "BEARISH"}
          </span>
          <span className="text-xs text-text-muted">
            SPY: <span className="font-mono text-text-primary">${regime.spy_close?.toFixed(2)}</span>
          </span>
          {regime.spy_ema20 && (
            <span className="text-xs text-text-muted">
              EMA20: <span className="font-mono text-text-primary">${regime.spy_ema20.toFixed(2)}</span>
            </span>
          )}
          {regime.spy_rsi != null && (
            <span className="text-xs text-text-muted">
              RSI: <span className={`font-mono ${regime.spy_rsi > 70 ? "text-bearish-text" : regime.spy_rsi < 30 ? "text-bullish-text" : "text-text-primary"}`}>
                {regime.spy_rsi.toFixed(1)}
              </span>
            </span>
          )}
          <div className="flex-1" />
          <button
            onClick={() => triggerScan.mutate()}
            disabled={triggerScan.isPending}
            className="text-xs font-medium text-accent hover:text-accent-hover disabled:opacity-50"
          >
            {triggerScan.isPending ? "Scanning..." : "Run EOD Scan"}
          </button>
        </div>
      )}

      {/* Watchlist Categories */}
      {categories && categories.length > 0 && (
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Watchlist Categories</h3>
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => (
              <div
                key={c.symbol}
                className={`rounded-lg border px-3 py-2 ${
                  c.category === "buy_zone" ? "border-bullish/30 bg-bullish/5" :
                  c.category === "strongest" ? "border-accent/30 bg-accent/5" :
                  c.category === "overbought" ? "border-warning/30 bg-warning/5" :
                  "border-border-subtle bg-surface-2"
                }`}
              >
                <p className="text-sm font-medium text-text-primary">{c.symbol}</p>
                <p className="text-[10px] text-text-muted capitalize">{c.category.replace("_", " ")}</p>
                {c.rsi != null && (
                  <p className={`font-mono text-[10px] ${c.rsi > 70 ? "text-bearish-text" : c.rsi < 30 ? "text-bullish-text" : "text-text-faint"}`}>
                    RSI {c.rsi.toFixed(0)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Swing Trades */}
      <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Active Swing Trades</h3>
        {activeTrades && activeTrades.length > 0 ? (
          <div className="space-y-2">
            {activeTrades.map((t) => {
              const pnl = t.current_price && t.entry_price
                ? ((t.current_price - t.entry_price) / t.entry_price) * 100
                : 0;
              const isExpanded = expandedSwing === t.id;
              const setupLabel = (t.alert_type || "").replace(/swing_/i, "").replace(/_/g, " ").toUpperCase() || "SWING SETUP";
              const stopLabel = (t.stop_type || "").replace(/_/g, " ");
              return (
                <div key={t.id} className="rounded-lg bg-surface-2/50 border border-border-subtle overflow-hidden">
                  <div
                    className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-surface-3/30 transition-colors"
                    onClick={() => setExpandedSwing(isExpanded ? null : t.id)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-bold px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/20">SWING</span>
                      <div>
                        <span className="font-medium text-text-primary">{t.symbol}</span>
                        <span className="text-xs text-text-muted ml-2">@ ${t.entry_price.toFixed(2)}</span>
                      </div>
                      <span className="text-[10px] text-text-faint">{isExpanded ? "▲" : "▼"}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      {t.current_price && (
                        <span className={`font-mono text-sm font-medium ${pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                          ${t.current_price.toFixed(2)} ({pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%)
                        </span>
                      )}
                      {t.current_rsi != null && (
                        <span className={`text-xs font-mono px-2 py-0.5 rounded ${
                          t.current_rsi > 70 ? "bg-bearish/10 text-bearish-text" :
                          t.current_rsi < 30 ? "bg-bullish/10 text-bullish-text" :
                          "bg-surface-3 text-text-muted"
                        }`}>
                          RSI {t.current_rsi.toFixed(0)}
                        </span>
                      )}
                      <span className="text-[10px] text-text-faint">{t.opened_date}</span>
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="px-4 pb-3 pt-1 border-t border-border-subtle bg-surface-1/50 space-y-2 text-xs">
                      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                        <div>
                          <span className="text-text-faint">Setup:</span>{" "}
                          <span className="text-accent font-medium">{setupLabel}</span>
                        </div>
                        <div>
                          <span className="text-text-faint">Direction:</span>{" "}
                          <span className="text-bullish-text font-medium">{t.direction}</span>
                        </div>
                        <div>
                          <span className="text-text-faint">Entry:</span>{" "}
                          <span className="text-text-primary font-mono">${t.entry_price.toFixed(2)}</span>
                          {t.entry_rsi != null && <span className="text-text-muted ml-1">(RSI {t.entry_rsi.toFixed(0)})</span>}
                        </div>
                        <div>
                          <span className="text-text-faint">Current:</span>{" "}
                          <span className={`font-mono ${pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                            ${(t.current_price || t.entry_price).toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-faint">Stop:</span>{" "}
                          <span className="text-bearish-text font-mono">{stopLabel || "—"}</span>
                        </div>
                        <div>
                          <span className="text-text-faint">Target:</span>{" "}
                          <span className="text-bullish-text font-mono">{t.target_type === "rsi_70" ? "RSI 70" : t.target_type || "—"}</span>
                        </div>
                      </div>
                      <div className="pt-1.5 border-t border-border-subtle/50 text-text-muted">
                        <span className="text-text-faint">Why this entry: </span>
                        {setupLabel === "EMA CROSSOVER 5 20" && "5 EMA crossed above 20 EMA — short-term momentum turning bullish."}
                        {setupLabel === "200MA RECLAIM" && "Price reclaimed the 200-day MA — long-term trend reversal signal."}
                        {setupLabel === "PULLBACK 20EMA" && "Price pulled back to the rising 20 EMA and held — continuation pattern."}
                        {setupLabel === "RSI 30 BOUNCE" && "RSI crossed above 30 from oversold — mean reversion bounce setup."}
                        {setupLabel === "200MA HOLD" && "Price wicked to 200 MA and closed above — key support held."}
                        {setupLabel === "50MA HOLD" && "Price wicked to rising 50 MA and closed above — intermediate support held."}
                        {setupLabel === "WEEKLY SUPPORT" && "Price bounced off prior week's low — weekly support zone holding."}
                        {!["EMA CROSSOVER 5 20", "200MA RECLAIM", "PULLBACK 20EMA", "RSI 30 BOUNCE", "200MA HOLD", "50MA HOLD", "WEEKLY SUPPORT"].includes(setupLabel) && "EOD swing scan detected a setup at a key technical level."}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-text-faint py-4 text-center">No active swing trades. Setups scan daily at market close.</p>
        )}
      </div>

      {/* Closed Swing Trades History */}
      {history && history.length > 0 && (
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
          <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">Swing Trade History</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] text-text-faint uppercase tracking-wider">
                  <th className="pb-2 pr-4">Symbol</th>
                  <th className="pb-2 pr-4">Entry</th>
                  <th className="pb-2 pr-4">Exit</th>
                  <th className="pb-2 pr-4">P&L</th>
                  <th className="pb-2 pr-4">RSI Entry</th>
                  <th className="pb-2 pr-4">Opened</th>
                  <th className="pb-2 pr-4">Closed</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id} className="border-t border-border-subtle/30">
                    <td className="py-2 pr-4 font-medium text-text-primary">{t.symbol}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">${t.entry_price.toFixed(2)}</td>
                    <td className="py-2 pr-4 font-mono text-text-secondary">{t.exit_price ? `$${t.exit_price.toFixed(2)}` : "—"}</td>
                    <td className={`py-2 pr-4 font-mono font-medium ${(t.pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      {t.pnl != null ? `${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(1)}%` : "—"}
                    </td>
                    <td className="py-2 pr-4 font-mono text-text-muted">{t.current_rsi?.toFixed(0) ?? "—"}</td>
                    <td className="py-2 pr-4 text-text-muted text-xs">{t.opened_date}</td>
                    <td className="py-2 pr-4 text-text-muted text-xs">{t.closed_date ?? "—"}</td>
                    <td className="py-2">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        t.status === "target_hit" ? "bg-bullish/10 text-bullish-text" :
                        t.status === "stopped" ? "bg-bearish/10 text-bearish-text" :
                        "bg-surface-3 text-text-muted"
                      }`}>
                        {t.status === "target_hit" ? "TARGET" : t.status === "stopped" ? "STOPPED" : t.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
