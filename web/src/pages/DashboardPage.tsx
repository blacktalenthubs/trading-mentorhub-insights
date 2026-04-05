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
  useOpenTrades, useCloseTrade, useIntraday, useMarketStatus,
} from "../api/hooks";
import type { Alert } from "../types";
import type { RealTrade } from "../api/hooks";
import ChartReplay from "../components/ChartReplay";
import { useFeatureGate } from "../hooks/useFeatureGate";
// TierGate used for future feature gating
import {
  Crosshair, Briefcase, Clock, BarChart3,
  FileText, Download, Lock,
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


/* ── Main Dashboard ───────────────────────────────────────────────── */

export default function DashboardPage() {
  const { data: summary } = useSessionSummary();
  const { data: alerts } = useAlertsToday();
  const { data: openTrades } = useOpenTrades();
  const [replayAlertId, setReplayAlertId] = useState<number | null>(null);
  const { visibleAlerts } = useFeatureGate();

  // Split alerts: actionable (BUY/SHORT without user_action) vs history
  const actionableAlerts = alerts?.filter((a) =>
    (a.direction === "BUY" || a.direction === "SHORT") && !a.user_action
  ) ?? [];
  const historyAlerts = alerts?.filter((a) =>
    a.user_action || a.direction === "SELL" || a.direction === "NOTICE"
  ) ?? [];

  // Tier-based alert visibility: free users see limited actionable alerts
  const visibleActionable = visibleAlerts != null
    ? actionableAlerts.slice(0, visibleAlerts)
    : actionableAlerts;
  const hiddenCount = actionableAlerts.length - visibleActionable.length;

  // Watchlist signals sorted by grade

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
                {visibleActionable.map((a) => (
                  <SignalCard key={a.id} alert={a} />
                ))}
                {hiddenCount > 0 && (
                  <div className="relative">
                    <div className="blur-sm pointer-events-none opacity-30">
                      <SignalCard alert={actionableAlerts[visibleAlerts!]} />
                    </div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="text-center p-4 bg-surface-2/90 backdrop-blur-sm rounded-xl border border-amber-500/20">
                        <Lock className="h-6 w-6 mx-auto mb-1.5 text-amber-400" />
                        <p className="text-sm text-text-primary font-semibold">+{hiddenCount} more signal{hiddenCount > 1 ? "s" : ""}</p>
                        <p className="text-xs text-text-muted mt-0.5 mb-2">Upgrade to see all alerts</p>
                        <Link to="/billing" className="inline-block bg-amber-500 hover:bg-amber-400 text-black text-xs font-bold px-4 py-1.5 rounded-lg transition-colors">
                          Upgrade to Pro
                        </Link>
                      </div>
                    </div>
                  </div>
                )}
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

            {/* Session Intelligence (4 cols) */}
            <div className="lg:col-span-4 bg-surface-1 border border-border-subtle rounded-xl flex flex-col overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border-subtle bg-surface-2/20">
                <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-accent" />
                  Session Intelligence
                </h3>
              </div>

              <div className="p-4 flex-1 flex flex-col gap-3">
                {(() => {
                  const took = alerts?.filter((a) => a.user_action === "took") ?? [];
                  const skipped = alerts?.filter((a) => a.user_action === "skipped") ?? [];
                  const targets = alerts?.filter((a) => a.alert_type?.includes("target")) ?? [];
                  const stops = alerts?.filter((a) => a.alert_type?.includes("stop")) ?? [];
                  const wr = targets.length + stops.length > 0
                    ? Math.round(targets.length / (targets.length + stops.length) * 100) : null;
                  const symbols = new Set(alerts?.map((a) => a.symbol) ?? []);
                  // Most active pattern
                  const patCounts: Record<string, number> = {};
                  (alerts ?? []).forEach((a) => { if (a.direction === "BUY" || a.direction === "SHORT") patCounts[a.alert_type] = (patCounts[a.alert_type] || 0) + 1; });
                  const topPattern = Object.entries(patCounts).sort((a, b) => b[1] - a[1])[0];

                  return (
                    <>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
                          <span className="text-[9px] text-text-faint uppercase">Took</span>
                          <p className="font-mono text-lg font-bold text-bullish-text">{took.length}</p>
                        </div>
                        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
                          <span className="text-[9px] text-text-faint uppercase">Skipped</span>
                          <p className="font-mono text-lg font-bold text-text-faint">{skipped.length}</p>
                        </div>
                        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
                          <span className="text-[9px] text-text-faint uppercase">Win Rate</span>
                          <p className="font-mono text-lg font-bold text-text-primary">{wr != null ? `${wr}%` : "—"}</p>
                        </div>
                        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
                          <span className="text-[9px] text-text-faint uppercase">Symbols</span>
                          <p className="font-mono text-lg font-bold text-text-primary">{symbols.size}</p>
                        </div>
                      </div>

                      {topPattern && (
                        <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
                          <span className="text-[9px] text-text-faint uppercase">Most Active Pattern</span>
                          <p className="text-sm font-medium text-text-primary mt-0.5">{topPattern[0].replace(/_/g, " ")}</p>
                          <span className="text-[10px] text-text-faint">{topPattern[1]} alerts today</span>
                        </div>
                      )}

                      <div className="flex flex-col gap-1.5 mt-auto">
                        <Link to="/trading" className="text-xs text-center py-2 bg-accent/10 text-accent hover:bg-accent/20 rounded-lg transition-colors font-medium">
                          Open Trading Terminal
                        </Link>
                        <Link to="/trades" className="text-xs text-center py-2 bg-surface-3 text-text-muted hover:bg-surface-4 rounded-lg transition-colors">
                          View Trade History
                        </Link>
                      </div>
                    </>
                  );
                })()}
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
              <div className="space-y-3">
                {/* Group alerts by symbol → then by pattern */}
                {Object.entries(
                  historyAlerts.reduce<Record<string, typeof historyAlerts>>((acc, a) => {
                    (acc[a.symbol] = acc[a.symbol] || []).push(a);
                    return acc;
                  }, {})
                ).sort((a, b) => b[1].length - a[1].length).map(([symbol, symbolAlerts]) => {
                  const tookCount = symbolAlerts.filter((a) => a.user_action === "took").length;
                  const skippedCount = symbolAlerts.filter((a) => a.user_action === "skipped").length;
                  const openCount = symbolAlerts.length - tookCount - skippedCount;

                  // Group by pattern type within symbol
                  const patternGroups = symbolAlerts.reduce<Record<string, typeof symbolAlerts>>((acc, a) => {
                    const pat = a.alert_type.replace(/_/g, " ");
                    (acc[pat] = acc[pat] || []).push(a);
                    return acc;
                  }, {});

                  return (
                    <details key={symbol} open className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
                      <summary className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-surface-2/30 transition-colors">
                        <div className="flex items-center gap-3">
                          <span className="font-bold text-text-primary">{symbol}</span>
                          <span className="text-[10px] text-text-faint">{symbolAlerts.length} alerts</span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px]">
                          {tookCount > 0 && <span className="text-bullish-text font-bold">{tookCount} took</span>}
                          {skippedCount > 0 && <span className="text-text-faint">{skippedCount} skip</span>}
                          {openCount > 0 && <span className="text-text-faint">{openCount} open</span>}
                        </div>
                      </summary>
                      <div className="border-t border-border-subtle/50 divide-y divide-border-subtle/20">
                        {Object.entries(patternGroups).map(([pattern, patAlerts]) => {
                          const patTook = patAlerts.filter((a) => a.user_action === "took").length;
                          const patSkipped = patAlerts.filter((a) => a.user_action === "skipped").length;
                          const dir = patAlerts[0]?.direction || "";
                          const latestAlert = patAlerts[0]; // most recent
                          const time = new Date(latestAlert.created_at).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });

                          return (
                            <div key={pattern} className="px-4 py-2.5 flex items-center gap-3 hover:bg-surface-2/20 transition-colors group">
                              {/* Direction indicator */}
                              <div className={`w-1 h-8 rounded-full shrink-0 ${
                                dir === "BUY" ? "bg-bullish" : dir === "SHORT" ? "bg-bearish" : "bg-text-faint"
                              }`} />

                              {/* Pattern name + count */}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm text-text-primary font-medium truncate">{pattern}</span>
                                  {patAlerts.length > 1 && <span className="text-[10px] text-text-faint">×{patAlerts.length}</span>}
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-text-faint">
                                  <span>{time}</span>
                                  <span>·</span>
                                  <span className="font-mono">${fmt(latestAlert.price)}</span>
                                </div>
                              </div>

                              {/* Direction badge */}
                              <span className={`text-[9px] font-bold px-2 py-0.5 rounded shrink-0 ${
                                dir === "BUY" ? "text-bullish-text bg-bullish/10 border border-bullish/20" :
                                dir === "SHORT" ? "text-bearish-text bg-bearish/10 border border-bearish/20" :
                                dir === "SELL" ? "text-warning-text bg-warning/10 border border-warning/20" :
                                "text-text-faint bg-surface-3 border border-border-subtle"
                              }`}>{dir === "BUY" ? "LONG" : dir}</span>

                              {/* Took/Skip badges */}
                              <div className="flex items-center gap-1 shrink-0">
                                {patTook > 0 && (
                                  <span className="text-[10px] font-bold text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">{patTook} took</span>
                                )}
                                {patSkipped > 0 && (
                                  <span className="text-[10px] text-text-faint bg-surface-3 px-1.5 py-0.5 rounded">{patSkipped} skip</span>
                                )}
                              </div>

                              {/* Replay button */}
                              <button
                                onClick={() => setReplayAlertId(latestAlert.id)}
                                className="text-xs text-accent hover:text-accent-hover opacity-60 group-hover:opacity-100 transition-opacity shrink-0 flex items-center gap-1"
                              >
                                ▶ Replay
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </details>
                  );
                })}
              </div>
            </section>
          )}

          {/* Empty state when no alerts at all */}
          {(!alerts || alerts.length === 0) && (
            <div className="flex flex-col items-center justify-center py-16 text-text-faint gap-3">
              <BarChart3 className="h-12 w-12 text-text-faint/20" />
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

      {/* Chart Replay Modal */}
      {replayAlertId && (
        <ChartReplay alertId={replayAlertId} onClose={() => setReplayAlertId(null)} />
      )}
    </div>
  );
}
