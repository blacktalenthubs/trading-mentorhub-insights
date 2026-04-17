/** Trade Review — review all alerts with symbol grouping and AI reasoning visible.
 *
 *  Changes from v1:
 *  - Tabs for outcome: All / Took / Skipped / Open
 *  - Group alerts by symbol (collapsible)
 *  - AI setup reason shown inline for pattern learning
 */

import { useState, useMemo } from "react";
import { useAlertsHistory } from "../api/hooks";
import ChartReplay from "../components/ChartReplay";
import type { Alert } from "../types";
import {
  Play,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Clock,
} from "lucide-react";

type ActionFilter = "all" | "took" | "skipped" | "open";

export default function TradeReviewPage() {
  const { data: alerts, isLoading } = useAlertsHistory(30);

  const [replayAlertId, setReplayAlertId] = useState<number | null>(null);
  const [actionFilter, setActionFilter] = useState<ActionFilter>("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [expandedSymbols, setExpandedSymbols] = useState<Set<string>>(new Set());
  const [expandedRowReason, setExpandedRowReason] = useState<Set<number>>(new Set());

  const sessionDates = useMemo(() => {
    if (!alerts) return [];
    return [...new Set(alerts.map((a) => a.session_date))].sort().reverse();
  }, [alerts]);

  const activeDate = selectedDate || sessionDates[0] || "";
  const dateIdx = sessionDates.indexOf(activeDate);

  // Filter alerts — exclude WAIT (no replay value), rules (AI-only page now)
  const filtered = useMemo(() => {
    if (!alerts) return [];
    let result = alerts
      .filter((a) => a.session_date === activeDate)
      .filter((a) => a.alert_type?.startsWith("ai_"))
      .filter((a) => a.alert_type !== "ai_scan_wait");

    if (actionFilter === "took") result = result.filter((a) => a.user_action === "took");
    if (actionFilter === "skipped") result = result.filter((a) => a.user_action === "skipped");
    if (actionFilter === "open") result = result.filter((a) => !a.user_action);

    return result;
  }, [alerts, activeDate, actionFilter]);

  // Group by symbol
  const groupedBySymbol = useMemo(() => {
    const groups: Record<string, Alert[]> = {};
    filtered.forEach((a) => {
      if (!groups[a.symbol]) groups[a.symbol] = [];
      groups[a.symbol].push(a);
    });
    // Sort each group by time descending
    Object.values(groups).forEach((arr) =>
      arr.sort((x, y) => new Date(y.created_at).getTime() - new Date(x.created_at).getTime())
    );
    return groups;
  }, [filtered]);

  // Symbols ordered by alert count desc, then alphabetical
  const symbolsOrdered = useMemo(
    () =>
      Object.keys(groupedBySymbol).sort((a, b) => {
        const diff = groupedBySymbol[b].length - groupedBySymbol[a].length;
        return diff !== 0 ? diff : a.localeCompare(b);
      }),
    [groupedBySymbol]
  );

  // Stats for the active date
  const dateAlerts = useMemo(
    () => alerts?.filter((a) => a.session_date === activeDate) ?? [],
    [alerts, activeDate]
  );
  const aiSignalCount = dateAlerts.filter(
    (a) => a.alert_type?.startsWith("ai_") && a.alert_type !== "ai_scan_wait"
  ).length;
  const tookCount = dateAlerts.filter((a) => a.user_action === "took").length;
  const skippedCount = dateAlerts.filter((a) => a.user_action === "skipped").length;
  const openCount = dateAlerts.filter(
    (a) =>
      a.alert_type?.startsWith("ai_") &&
      a.alert_type !== "ai_scan_wait" &&
      !a.user_action
  ).length;

  const fmt = (n: number) =>
    n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const formatDate = (d: string) => {
    const date = new Date(d + "T12:00:00");
    return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  };

  function toggleSymbol(sym: string) {
    setExpandedSymbols((prev) => {
      const next = new Set(prev);
      if (next.has(sym)) next.delete(sym);
      else next.add(sym);
      return next;
    });
  }

  function toggleReason(id: number) {
    setExpandedRowReason((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function expandAll() {
    setExpandedSymbols(new Set(symbolsOrdered));
  }
  function collapseAll() {
    setExpandedSymbols(new Set());
  }

  // Full-screen replay
  if (replayAlertId) {
    return (
      <div className="fixed inset-0 z-50 bg-surface-0">
        <ChartReplay alertId={replayAlertId} onClose={() => setReplayAlertId(null)} />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5 p-4 md:p-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-text-primary">Trade Review</h1>
        <p className="text-xs text-text-muted mt-1">
          Grouped by symbol · AI reasoning visible · Replay any alert to study the pattern.
        </p>
      </div>

      {/* Date Navigation */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => dateIdx < sessionDates.length - 1 && setSelectedDate(sessionDates[dateIdx + 1])}
          disabled={dateIdx >= sessionDates.length - 1}
          className="p-1.5 rounded-lg border border-border-subtle hover:bg-surface-2 disabled:opacity-30 transition-colors"
        >
          <ChevronLeft className="h-4 w-4 text-text-secondary" />
        </button>
        <span className="text-sm font-bold text-text-primary min-w-[140px] text-center">
          {activeDate ? formatDate(activeDate) : "No data"}
        </span>
        <button
          onClick={() => dateIdx > 0 && setSelectedDate(sessionDates[dateIdx - 1])}
          disabled={dateIdx <= 0}
          className="p-1.5 rounded-lg border border-border-subtle hover:bg-surface-2 disabled:opacity-30 transition-colors"
        >
          <ChevronRight className="h-4 w-4 text-text-secondary" />
        </button>

        {/* Expand/Collapse all */}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={expandAll}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            Expand all
          </button>
          <span className="text-text-faint text-[10px]">·</span>
          <button
            onClick={collapseAll}
            className="text-[10px] text-text-muted hover:text-accent"
          >
            Collapse all
          </button>
        </div>
      </div>

      {/* Outcome tabs */}
      <div className="flex rounded-lg border border-border-subtle overflow-hidden w-fit">
        {(
          [
            ["all", "All", aiSignalCount],
            ["took", "Took", tookCount],
            ["skipped", "Skipped", skippedCount],
            ["open", "Open", openCount],
          ] as const
        ).map(([val, label, count]) => (
          <button
            key={val}
            onClick={() => setActionFilter(val)}
            className={`px-4 py-1.5 text-[11px] font-medium transition-colors flex items-center gap-1.5 ${
              actionFilter === val
                ? "bg-accent/15 text-accent"
                : "text-text-muted hover:bg-surface-2"
            }`}
          >
            {label}
            <span className="text-[9px] bg-surface-2 rounded px-1 py-0.5">{count}</span>
          </button>
        ))}
      </div>

      {/* Grouped list */}
      {isLoading ? (
        <div className="text-center py-12 text-text-muted text-sm">Loading alerts...</div>
      ) : symbolsOrdered.length === 0 ? (
        <div className="text-center py-12 text-text-muted text-sm">
          No alerts match your filters.
        </div>
      ) : (
        <div className="space-y-2">
          {symbolsOrdered.map((symbol) => {
            const rows = groupedBySymbol[symbol];
            const isExpanded = expandedSymbols.has(symbol);
            const tookN = rows.filter((r) => r.user_action === "took").length;
            const skipN = rows.filter((r) => r.user_action === "skipped").length;
            const openN = rows.filter((r) => !r.user_action).length;
            return (
              <div
                key={symbol}
                className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden"
              >
                {/* Group header */}
                <button
                  onClick={() => toggleSymbol(symbol)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-2/30 transition-colors"
                >
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-text-muted shrink-0" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-text-muted shrink-0" />
                  )}
                  <span className="text-sm font-bold text-text-primary">{symbol}</span>
                  <span className="text-[10px] text-text-faint">
                    {rows.length} alert{rows.length !== 1 ? "s" : ""}
                  </span>
                  <div className="ml-auto flex items-center gap-2 text-[10px] text-text-muted">
                    {tookN > 0 && (
                      <span className="text-bullish-text">
                        <CheckCircle className="h-3 w-3 inline mr-0.5" />
                        {tookN} took
                      </span>
                    )}
                    {skipN > 0 && (
                      <span className="text-text-faint">
                        <XCircle className="h-3 w-3 inline mr-0.5" />
                        {skipN} skip
                      </span>
                    )}
                    {openN > 0 && (
                      <span className="text-text-faint">
                        <Clock className="h-3 w-3 inline mr-0.5" />
                        {openN} open
                      </span>
                    )}
                  </div>
                </button>

                {/* Expanded rows */}
                {isExpanded && (
                  <div className="border-t border-border-subtle/30 divide-y divide-border-subtle/30">
                    {rows.map((alert) => {
                      const time = new Date(alert.created_at).toLocaleTimeString("en-US", {
                        hour: "2-digit",
                        minute: "2-digit",
                      });
                      const typeName = alert.alert_type?.replace(/_/g, " ") || "unknown";
                      const reasonOpen = expandedRowReason.has(alert.id);
                      const message = alert.message || "";

                      return (
                        <div
                          key={alert.id}
                          className="px-4 py-3 hover:bg-surface-2/30 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <div
                              className={`w-1 h-10 rounded-full shrink-0 ${
                                alert.direction === "BUY"
                                  ? "bg-bullish"
                                  : alert.direction === "SHORT"
                                  ? "bg-bearish"
                                  : alert.direction === "SELL"
                                  ? "bg-warning"
                                  : "bg-text-faint"
                              }`}
                            />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-[11px] text-text-secondary">{typeName}</span>
                                <span className="text-[10px] text-text-faint">{time}</span>
                              </div>
                              <div className="flex items-center gap-2 text-[10px] text-text-faint mt-0.5 flex-wrap">
                                <span className="font-mono">${fmt(alert.price)}</span>
                                {alert.entry && (
                                  <>
                                    <span>·</span>
                                    <span>Entry ${fmt(alert.entry)}</span>
                                  </>
                                )}
                                {alert.stop && (
                                  <>
                                    <span>·</span>
                                    <span>Stop ${fmt(alert.stop)}</span>
                                  </>
                                )}
                                {alert.target_1 && (
                                  <>
                                    <span>·</span>
                                    <span>T1 ${fmt(alert.target_1)}</span>
                                  </>
                                )}
                                {alert.confidence && (
                                  <>
                                    <span>·</span>
                                    <span className="uppercase">{alert.confidence}</span>
                                  </>
                                )}
                              </div>
                            </div>
                            <span
                              className={`text-[9px] font-bold px-2 py-0.5 rounded shrink-0 ${
                                alert.direction === "BUY"
                                  ? "text-bullish-text bg-bullish/10 border border-bullish/20"
                                  : alert.direction === "SHORT"
                                  ? "text-bearish-text bg-bearish/10 border border-bearish/20"
                                  : alert.direction === "SELL"
                                  ? "text-warning-text bg-warning/10 border border-warning/20"
                                  : "text-text-faint bg-surface-3 border border-border-subtle"
                              }`}
                            >
                              {alert.direction === "BUY" ? "LONG" : alert.direction}
                            </span>
                            <div className="shrink-0 w-14 text-center">
                              {alert.user_action === "took" && (
                                <span className="inline-flex items-center gap-1 text-[10px] font-bold text-bullish-text">
                                  <CheckCircle className="h-3 w-3" />
                                  Took
                                </span>
                              )}
                              {alert.user_action === "skipped" && (
                                <span className="inline-flex items-center gap-1 text-[10px] text-text-faint">
                                  <XCircle className="h-3 w-3" />
                                  Skip
                                </span>
                              )}
                              {!alert.user_action && (
                                <span className="inline-flex items-center gap-1 text-[10px] text-text-faint">
                                  <Clock className="h-3 w-3" />
                                  Open
                                </span>
                              )}
                            </div>
                            <button
                              onClick={() => setReplayAlertId(alert.id)}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-accent bg-accent/10 border border-accent/20 hover:bg-accent/20 transition-all shrink-0"
                            >
                              <Play className="h-3 w-3" />
                              Replay
                            </button>
                          </div>
                          {/* AI reason */}
                          {message && (
                            <button
                              onClick={() => toggleReason(alert.id)}
                              className="mt-2 ml-4 text-[11px] text-text-muted text-left w-full hover:text-text-secondary transition-colors"
                            >
                              <span className="text-text-faint">Reason: </span>
                              {reasonOpen ? (
                                <span>{message}</span>
                              ) : (
                                <span className="line-clamp-1">{message}</span>
                              )}
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
