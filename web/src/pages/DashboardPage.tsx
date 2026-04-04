/** Dashboard — Trading Command Center.
 *
 *  Layout:
 *    Header:  Market regime (SPY/QQQ) + session stats + session P&L
 *    Hero:    Priority Signals — large actionable BUY/SHORT cards with Took/Skip
 *    Bottom:  Active Positions table (left 8col) + AI Early Detection / Watchlist (right 4col)
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useAlertsToday, useSessionSummary, useAckAlert,
  useOpenTrades, useCloseTrade, useIntraday, useMarketStatus, useScanner,
} from "../api/hooks";
import type { Alert, SignalResult } from "../types";
import type { RealTrade } from "../api/hooks";
import {
  Crosshair, Radar, Briefcase, Clock,
  FileText, Download,
} from "lucide-react";

/* ── helpers ──────────────────────────────────────────────────────── */

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function fmtDollar(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function livePnl(trade: RealTrade, currentPrice: number): number {
  if (trade.direction === "BUY") return (currentPrice - trade.entry_price) * trade.shares;
  return (trade.entry_price - currentPrice) * trade.shares;
}

/* ── Market Regime Header ─────────────────────────────────────────── */

function MarketHeader({ summary }: { summary: any }) {
  const { data: market } = useMarketStatus();

  const statusBadge = market?.is_open
    ? { bg: "bg-bullish/10 border-bullish/20", dot: "bg-bullish", text: "text-bullish-text", label: "Market Open" }
    : market?.is_premarket
    ? { bg: "bg-warning/10 border-warning/20", dot: "bg-warning", text: "text-warning-text", label: "Pre-Market" }
    : { bg: "bg-surface-3 border-border-subtle", dot: "bg-text-faint", text: "text-text-faint", label: "Closed" };

  const winRate = summary
    ? summary.target_1_hits + summary.target_2_hits > 0
      ? ((summary.target_1_hits + summary.target_2_hits) /
          Math.max(summary.target_1_hits + summary.target_2_hits + summary.stopped_out, 1)) * 100
      : 0
    : 0;

  return (
    <header className="h-16 border-b border-border-subtle flex items-center justify-between px-6 shrink-0 bg-surface-1/30 backdrop-blur-sm">
      <div className="flex items-center gap-5">
        <div className={`flex items-center gap-2 ${statusBadge.bg} border px-3 py-1.5 rounded-full`}>
          <div className={`w-2 h-2 rounded-full ${statusBadge.dot} animate-pulse`} />
          <span className={`text-[10px] font-mono font-bold tracking-widest uppercase ${statusBadge.text}`}>{statusBadge.label}</span>
        </div>
      </div>

      {/* Session stats compact */}
      <div className="flex items-center gap-5 font-mono text-sm">
        {summary && (
          <>
            <div className="flex items-center gap-4 bg-surface-2/50 border border-border-subtle rounded-lg px-1.5 py-1">
              <div className="px-2.5 py-0.5 flex flex-col items-center">
                <span className="text-[9px] text-text-faint uppercase">Signals</span>
                <span className="text-sm font-bold text-text-primary">{summary.total_alerts}</span>
              </div>
              <div className="w-px h-5 bg-border-subtle" />
              <div className="px-2.5 py-0.5 flex flex-col items-center">
                <span className="text-[9px] text-text-faint uppercase">Taken</span>
                <span className="text-sm font-bold text-text-primary">{summary.target_1_hits + summary.target_2_hits + summary.stopped_out}</span>
              </div>
              <div className="w-px h-5 bg-border-subtle" />
              <div className="px-2.5 py-0.5 flex flex-col items-center">
                <span className="text-[9px] text-bullish-text uppercase">Win</span>
                <span className="text-sm font-bold text-bullish-text">{winRate.toFixed(0)}%</span>
              </div>
              <div className="w-px h-5 bg-border-subtle" />
              <div className="px-2.5 py-0.5 flex flex-col items-center">
                <span className="text-[9px] text-bullish-text uppercase">T1/T2</span>
                <span className="text-sm font-bold text-bullish-text">{summary.target_1_hits + summary.target_2_hits}</span>
              </div>
              <div className="w-px h-5 bg-border-subtle" />
              <div className="px-2.5 py-0.5 flex flex-col items-center">
                <span className="text-[9px] text-bearish-text uppercase">Stops</span>
                <span className="text-sm font-bold text-bearish-text">{summary.stopped_out}</span>
              </div>
            </div>
          </>
        )}

        <Link
          to="/trading"
          className="flex items-center gap-1.5 bg-surface-3 hover:bg-surface-4 border border-border-subtle text-text-primary text-xs font-semibold px-4 py-2 rounded-lg transition-colors"
        >
          <Crosshair className="h-3.5 w-3.5" />
          Open Trading
        </Link>
      </div>
    </header>
  );
}

/* ── Priority Signal Card (Hero) ──────────────────────────────────── */

function SignalCard({ alert: a }: { alert: Alert }) {
  const ack = useAckAlert();
  const [expanded, setExpanded] = useState(false);

  const isBuy = a.direction === "BUY";
  const dirColor = isBuy ? "bullish" : "bearish";
  const rr = a.entry && a.stop && a.target_1
    ? ((a.target_1 - a.entry) / Math.abs(a.entry - a.stop)).toFixed(1)
    : null;

  return (
    <div className={`relative bg-surface-1 rounded-lg border border-border-subtle overflow-hidden ${
      isBuy ? "border-l-2 border-l-bullish" : "border-l-2 border-l-bearish"
    }`}>
      <div className="px-4 py-3">
        {/* Row 1: Symbol, direction, type, price, actions */}
        <div className="flex items-center gap-3">
          <span className="font-bold text-sm text-text-primary w-16 shrink-0">{a.symbol}</span>
          <span className={`bg-${dirColor}-muted text-${dirColor}-text px-1.5 py-0.5 rounded text-[10px] font-bold uppercase shrink-0`}>
            {a.direction}
          </span>
          <span className="text-xs text-text-muted truncate flex-1">{a.alert_type.replace(/_/g, " ")}</span>

          {/* Levels inline */}
          {a.entry != null && (
            <div className="hidden sm:flex items-center gap-3 text-[11px] font-mono shrink-0">
              <span className="text-text-primary">${fmt(a.entry)}</span>
              <span className="text-bearish-text">${fmt(a.stop)}</span>
              <span className="text-bullish-text">${fmt(a.target_1)}</span>
              {rr && <span className="text-text-faint">{rr}R</span>}
            </div>
          )}

          <span className="font-mono text-sm font-bold text-text-primary shrink-0">${fmt(a.price)}</span>

          {/* Took / Skip */}
          <div className="flex items-center gap-1.5 shrink-0 ml-2">
            <button
              onClick={() => ack.mutate({ id: a.id, action: "took" })}
              className={`font-bold text-xs py-1.5 px-4 rounded-md transition-all ${
                isBuy
                  ? "bg-bullish hover:bg-bullish/80 text-surface-0"
                  : "bg-bearish hover:bg-bearish/80 text-white"
              }`}
            >
              Took
            </button>
            <button
              onClick={() => ack.mutate({ id: a.id, action: "skipped" })}
              className="text-xs py-1.5 px-3 border border-border-subtle hover:bg-surface-3 text-text-muted rounded-md transition-colors"
            >
              Skip
            </button>
            {a.message && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[10px] text-text-faint hover:text-text-muted px-1"
                title="Show AI analysis"
              >
                {expanded ? "▲" : "▼"}
              </button>
            )}
          </div>
        </div>

        {/* Expandable AI rationale */}
        {expanded && a.message && (
          <p className="mt-2 text-xs text-text-secondary leading-relaxed pl-[76px] border-t border-border-subtle/50 pt-2">{a.message}</p>
        )}
      </div>
    </div>
  );
}

/* ── Actioned alert (expandable history) ──────────────────────────── */

function ActionedAlert({ alert: a }: { alert: Alert }) {
  const [expanded, setExpanded] = useState(false);
  const time = new Date(a.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  const isTarget = a.alert_type.includes("target");
  const isStop = a.alert_type.includes("stop");
  const rr = a.entry && a.stop && a.target_1
    ? ((a.target_1 - a.entry) / Math.abs(a.entry - a.stop)).toFixed(1)
    : null;

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      className={`rounded-lg border cursor-pointer transition-all ${
        a.user_action === "took" ? "bg-bullish/[0.03] border-bullish/10 hover:border-bullish/25" :
        a.user_action === "skipped" ? "bg-surface-2/30 border-border-subtle/30 hover:border-border-subtle opacity-70 hover:opacity-100" :
        isTarget ? "bg-bullish/[0.03] border-bullish/10 hover:border-bullish/25" :
        isStop ? "bg-bearish/[0.03] border-bearish/10 hover:border-bearish/25" :
        "bg-surface-2/30 border-border-subtle/30 hover:border-border-subtle"
      }`}
    >
      {/* Collapsed row */}
      <div className="flex items-center gap-3 px-4 py-2.5">
        <div className={`w-1 h-8 rounded-full shrink-0 ${
          a.user_action === "took" ? "bg-bullish" :
          a.user_action === "skipped" ? "bg-text-faint" :
          isTarget ? "bg-bullish" : isStop ? "bg-bearish" : "bg-text-faint"
        }`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-text-primary">{a.symbol}</span>
            <span className={`text-[9px] font-bold uppercase ${
              a.direction === "BUY" ? "text-bullish-text" : a.direction === "SHORT" ? "text-bearish-text" : "text-text-muted"
            }`}>{a.direction}</span>
            <span className="text-[10px] text-text-faint">{a.alert_type.replace(/_/g, " ")}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {a.user_action && (
            <span className={`text-[10px] font-bold uppercase ${a.user_action === "took" ? "text-bullish-text" : "text-text-faint"}`}>
              {a.user_action}
            </span>
          )}
          <span className="font-mono text-xs text-text-faint">{time}</span>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="border-t border-border-subtle/30 px-4 py-3 space-y-2.5">
          {/* Price + levels */}
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
            <span className="text-text-muted">Price: <span className="font-mono text-text-primary">${fmt(a.price)}</span></span>
            {a.entry != null && <span className="text-text-muted">Entry: <span className="font-mono text-text-primary">${fmt(a.entry)}</span></span>}
            {a.stop != null && <span className="text-text-muted">Stop: <span className="font-mono text-bearish-text">${fmt(a.stop)}</span></span>}
            {a.target_1 != null && <span className="text-text-muted">T1: <span className="font-mono text-bullish-text">${fmt(a.target_1)}</span></span>}
            {a.target_2 != null && <span className="text-text-muted">T2: <span className="font-mono text-bullish-text">${fmt(a.target_2)}</span></span>}
            {rr && <span className="text-text-muted">R:R: <span className="font-mono text-text-primary">1:{rr}</span></span>}
          </div>
          {/* Message */}
          {a.message && (
            <p className="text-xs text-text-secondary leading-relaxed">{a.message}</p>
          )}
          {/* Confidence + timestamp */}
          <div className="flex items-center gap-3 text-[10px] text-text-faint">
            {a.confidence && <span>{a.confidence} confidence</span>}
            <span>{a.created_at}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Position Row ─────────────────────────────────────────────────── */

function PositionRow({ trade }: { trade: RealTrade }) {
  const { data: bars } = useIntraday(trade.symbol);
  const closeTrade = useCloseTrade();
  const lastPrice = bars?.length ? bars[bars.length - 1].close : null;
  const pnl = lastPrice != null ? livePnl(trade, lastPrice) : null;
  const pnlPct = lastPrice != null && trade.entry_price > 0
    ? ((lastPrice - trade.entry_price) / trade.entry_price) * 100 * (trade.direction === "BUY" ? 1 : -1)
    : null;

  function handleClose() {
    if (!lastPrice) return;
    closeTrade.mutate({ id: trade.id, exit_price: lastPrice, notes: "Closed from dashboard" });
  }

  return (
    <tr className="border-b border-border-subtle/30 hover:bg-surface-2/30 transition-colors group">
      <td className="px-5 py-3">
        <div className="flex items-center gap-2.5">
          <div className={`w-1.5 h-6 rounded-full ${trade.direction === "BUY" ? "bg-bullish" : "bg-bearish"}`} />
          <div>
            <span className="font-bold text-text-primary">{trade.symbol}</span>
            <span className={`ml-2 text-[10px] font-bold uppercase ${trade.direction === "BUY" ? "text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded" : "text-bearish-text bg-bearish/10 px-1.5 py-0.5 rounded"}`}>
              {trade.direction === "BUY" ? "Long" : "Short"}
            </span>
          </div>
        </div>
      </td>
      <td className="px-5 py-3 text-right font-mono text-text-muted">{trade.shares}</td>
      <td className="px-5 py-3 text-right font-mono text-text-muted">${fmt(trade.entry_price)}</td>
      <td className="px-5 py-3 text-right font-mono text-text-primary">
        {lastPrice != null ? `$${fmt(lastPrice)}` : "—"}
      </td>
      <td className="px-5 py-3 text-right">
        {pnl != null ? (
          <div className="flex flex-col items-end">
            <span className={`font-mono font-bold ${pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
              {fmtDollar(pnl)}
            </span>
            {pnlPct != null && (
              <span className={`text-[10px] font-mono ${pnl >= 0 ? "text-bullish-text/70" : "text-bearish-text/70"}`}>
                {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
              </span>
            )}
          </div>
        ) : "—"}
      </td>
      <td className="px-3 py-3">
        <button
          onClick={handleClose}
          disabled={!lastPrice || closeTrade.isPending}
          className="opacity-0 group-hover:opacity-100 text-[10px] font-bold text-bearish-text bg-bearish/10 hover:bg-bearish/20 border border-bearish/20 px-2.5 py-1 rounded transition-all disabled:opacity-30"
        >
          {closeTrade.isPending ? "..." : "Close"}
        </button>
      </td>
    </tr>
  );
}

/* ── Watchlist Scanner Item ───────────────────────────────────────── */

function ScannerItem({ signal: s }: { signal: SignalResult }) {
  return (
    <Link
      to="/trading"
      className="flex items-center justify-between p-3 rounded-lg hover:bg-surface-2/50 border border-transparent hover:border-border-subtle transition-colors group"
    >
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-surface-3 border border-border-subtle flex items-center justify-center text-[10px] font-bold text-text-secondary">
          {s.symbol.slice(0, 4)}
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-sm text-text-primary group-hover:text-accent transition-colors">{s.symbol}</span>
          <span className="text-[10px] text-text-faint">{s.action_label} · {s.pattern}</span>
        </div>
      </div>
      <div className="text-right">
        <span className="block font-mono text-sm text-text-primary">${fmt(s.close)}</span>
        <span className="text-[10px] text-text-faint font-mono">{s.grade} · {fmt(s.rr_ratio, 1)}R</span>
      </div>
    </Link>
  );
}

/* ── Main Dashboard ───────────────────────────────────────────────── */

export default function DashboardPage() {
  const { data: summary } = useSessionSummary();
  const { data: alerts } = useAlertsToday();
  const { data: openTrades } = useOpenTrades();
  const { data: signals } = useScanner();

  // Split alerts: actionable (BUY/SHORT without user_action) vs history
  const actionableAlerts = alerts?.filter((a) =>
    (a.direction === "BUY" || a.direction === "SHORT") && !a.user_action
  ) ?? [];
  const historyAlerts = alerts?.filter((a) =>
    a.user_action || a.direction === "SELL" || a.direction === "NOTICE"
  ) ?? [];

  // Watchlist signals sorted by grade
  const watchSignals = signals?.filter((s) => s.action_label !== "No Setup").slice(0, 6) ?? [];

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <MarketHeader summary={summary} />

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-[1600px] mx-auto w-full flex flex-col gap-7">

          {/* ── SECTION 1: Priority Signals (Hero) ── */}
          {actionableAlerts.length > 0 && (
            <section>
              <div className="flex items-end justify-between mb-4">
                <div>
                  <h1 className="text-xl font-bold text-text-primary flex items-center gap-2.5">
                    Priority Signals
                    <span className="bg-accent/10 text-accent text-[10px] px-2 py-0.5 rounded border border-accent/20 font-mono">
                      {actionableAlerts.length} ACTIVE
                    </span>
                  </h1>
                  <p className="text-text-muted text-xs mt-1">High-conviction setups — take action or dismiss</p>
                </div>
              </div>

              <div className="flex flex-col gap-2">
                {actionableAlerts.map((a) => (
                  <SignalCard key={a.id} alert={a} />
                ))}
              </div>
            </section>
          )}

          {/* ── SECTION 2: Positions + Watchlist Radar ── */}
          <section className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Active Positions (8 cols) */}
            <div className="lg:col-span-8 bg-surface-1 border border-border-subtle rounded-xl flex flex-col overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border-subtle flex justify-between items-center bg-surface-2/20">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <Briefcase className="h-4 w-4 text-text-muted" />
                  Active Positions
                  {openTrades && openTrades.length > 0 && (
                    <span className="text-[10px] text-text-faint font-normal">({openTrades.length})</span>
                  )}
                </h3>
                <Link to="/trades" className="text-xs text-accent hover:text-accent-hover font-mono">
                  View All →
                </Link>
              </div>

              {openTrades && openTrades.length > 0 ? (
                <div className="overflow-auto flex-1">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-widest text-text-faint border-b border-border-subtle/50 bg-surface-0/50">
                        <th className="px-5 py-2.5 font-medium">Symbol</th>
                        <th className="px-5 py-2.5 font-medium text-right">Size</th>
                        <th className="px-5 py-2.5 font-medium text-right">Entry</th>
                        <th className="px-5 py-2.5 font-medium text-right">Last</th>
                        <th className="px-5 py-2.5 font-medium text-right">P&L</th>
                        <th className="px-3 py-2.5 font-medium"></th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      {openTrades.map((t) => <PositionRow key={t.id} trade={t} />)}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center py-12 text-text-faint gap-2">
                  <Briefcase className="h-8 w-8 text-text-faint/30" />
                  <p className="text-sm">No open positions</p>
                  <Link to="/trading" className="text-xs text-accent hover:text-accent-hover">Open Trading Terminal</Link>
                </div>
              )}
            </div>

            {/* Watchlist Radar (4 cols) */}
            <div className="lg:col-span-4 bg-surface-1 border border-border-subtle rounded-xl flex flex-col overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border-subtle flex justify-between items-center bg-surface-2/20">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <Radar className="h-4 w-4 text-accent" />
                  Watchlist Radar
                </h3>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-accent" />
                </span>
              </div>

              <div className="p-3 flex-1 flex flex-col gap-1 overflow-auto">
                {watchSignals.length > 0 ? (
                  <>
                    <p className="text-[10px] text-text-faint px-3 mb-1">Symbols with active setups on your watchlist</p>
                    {watchSignals.map((s) => <ScannerItem key={s.symbol} signal={s} />)}
                  </>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center text-text-faint gap-2">
                    <Radar className="h-6 w-6 text-text-faint/30" />
                    <p className="text-xs">No setups detected</p>
                  </div>
                )}

                <Link
                  to="/trading"
                  className="mt-auto mx-2 mb-1 py-2 text-xs font-medium text-text-muted hover:text-text-primary bg-surface-2/30 hover:bg-surface-3 border border-border-subtle rounded-lg transition-colors flex items-center justify-center gap-1.5"
                >
                  <Crosshair className="h-3 w-3" /> Full Scanner
                </Link>
              </div>
            </div>
          </section>

          {/* ── SECTION 3: Alert History (expandable + exportable) ── */}
          {historyAlerts.length > 0 && (
            <section>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-text-secondary flex items-center gap-2">
                  <Clock className="h-4 w-4 text-text-faint" />
                  Today's Activity
                  <span className="text-[10px] text-text-faint font-normal">({historyAlerts.length})</span>
                  <span className="text-[10px] text-text-faint font-normal">· Click to expand</span>
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      // CSV export
                      if (!alerts || alerts.length === 0) return;
                      const header = "Time,Symbol,Direction,Type,Price,Entry,Stop,T1,T2,Confidence,Action,Message\n";
                      const rows = alerts.map((a) =>
                        `${a.created_at},${a.symbol},${a.direction},${a.alert_type},${a.price},${a.entry ?? ""},${a.stop ?? ""},${a.target_1 ?? ""},${a.target_2 ?? ""},${a.confidence ?? ""},${a.user_action ?? ""},${(a.message || "").replace(/,/g, ";")}`
                      ).join("\n");
                      const blob = new Blob([header + rows], { type: "text/csv" });
                      const url = URL.createObjectURL(blob);
                      const link = document.createElement("a");
                      link.href = url;
                      link.download = `tradesignal_alerts_${new Date().toISOString().slice(0, 10)}.csv`;
                      link.click();
                      URL.revokeObjectURL(url);
                    }}
                    className="flex items-center gap-1.5 text-[10px] text-text-muted hover:text-text-secondary bg-surface-2/50 hover:bg-surface-3 border border-border-subtle px-2.5 py-1.5 rounded transition-colors"
                  >
                    <Download className="h-3 w-3" />
                    CSV
                  </button>
                  <a
                    href="/api/v1/alerts/pdf"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5 text-[10px] text-text-muted hover:text-text-secondary bg-surface-2/50 hover:bg-surface-3 border border-border-subtle px-2.5 py-1.5 rounded transition-colors"
                  >
                    <FileText className="h-3 w-3" />
                    PDF Report
                  </a>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
                {historyAlerts.slice(0, 12).map((a) => (
                  <ActionedAlert key={a.id} alert={a} />
                ))}
              </div>
            </section>
          )}

          {/* Empty state when no alerts at all */}
          {(!alerts || alerts.length === 0) && (
            <div className="flex flex-col items-center justify-center py-16 text-text-faint gap-3">
              <Radar className="h-12 w-12 text-text-faint/20" />
              <p className="text-lg font-medium text-text-muted">No signals yet today</p>
              <p className="text-sm text-text-faint text-center max-w-md">
                The scanner checks your watchlist every 3 minutes during market hours.
                Alerts appear here when structural setups are detected.
              </p>
              <div className="flex gap-3 mt-2">
                <Link to="/trading" className="text-sm bg-accent hover:bg-accent-hover text-white px-4 py-2 rounded-lg transition-colors">
                  Open Trading Terminal
                </Link>
                <Link to="/settings" className="text-sm text-text-muted hover:text-text-secondary border border-border-subtle px-4 py-2 rounded-lg transition-colors">
                  Manage Watchlist
                </Link>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
