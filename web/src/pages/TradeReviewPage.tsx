/** Trade Review — dedicated page for replaying and reviewing all alerts.
 *
 *  Shows all alerts (AI scan + rule-based) with replay capability.
 *  Replaces the hidden "Replay" buttons buried in the dashboard.
 */

import { useState, useMemo } from "react";
import { useAlertsHistory } from "../api/hooks";
import ChartReplay from "../components/ChartReplay";
import {
  Play,
  Filter,
  ChevronLeft,
  ChevronRight,
  Brain,
  Crosshair,
  CheckCircle,
  XCircle,
  Clock,
} from "lucide-react";

type SourceFilter = "all" | "ai" | "rules";
type ActionFilter = "all" | "took" | "skipped" | "open";

export default function TradeReviewPage() {
  const { data: alerts, isLoading } = useAlertsHistory(30);

  const [replayAlertId, setReplayAlertId] = useState<number | null>(null);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all");
  const [actionFilter, setActionFilter] = useState<ActionFilter>("all");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Get unique session dates
  const sessionDates = useMemo(() => {
    if (!alerts) return [];
    const dates = [...new Set(alerts.map((a) => a.session_date))].sort().reverse();
    return dates;
  }, [alerts]);

  // Default to most recent date
  const activeDate = selectedDate || sessionDates[0] || "";
  const dateIdx = sessionDates.indexOf(activeDate);

  // Filter alerts — exclude WAIT (no replay value)
  const filtered = useMemo(() => {
    if (!alerts) return [];
    let result = alerts
      .filter((a) => a.session_date === activeDate)
      .filter((a) => a.alert_type !== "ai_scan_wait");

    if (sourceFilter === "ai") result = result.filter((a) => a.alert_type?.startsWith("ai_"));
    if (sourceFilter === "rules") result = result.filter((a) => !a.alert_type?.startsWith("ai_"));

    if (actionFilter === "took") result = result.filter((a) => a.user_action === "took");
    if (actionFilter === "skipped") result = result.filter((a) => a.user_action === "skipped");
    if (actionFilter === "open") result = result.filter((a) => !a.user_action);

    return result;
  }, [alerts, activeDate, sourceFilter, actionFilter]);

  // Stats for the active date
  const dateAlerts = useMemo(() => alerts?.filter((a) => a.session_date === activeDate) ?? [], [alerts, activeDate]);
  const aiSignalCount = dateAlerts.filter((a) =>
    a.alert_type?.startsWith("ai_") && a.alert_type !== "ai_scan_wait"
  ).length;
  const aiWaitCount = dateAlerts.filter((a) => a.alert_type === "ai_scan_wait").length;
  const ruleCount = dateAlerts.filter((a) => !a.alert_type?.startsWith("ai_")).length;
  const tookCount = dateAlerts.filter((a) => a.user_action === "took").length;
  const skippedCount = dateAlerts.filter((a) => a.user_action === "skipped").length;

  const fmt = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const formatDate = (d: string) => {
    const date = new Date(d + "T12:00:00");
    return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  };

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
          Replay any alert to evaluate entries, exits, and pattern recognition.
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

        {/* Quick stats */}
        <div className="flex items-center gap-3 ml-auto text-[10px] text-text-muted">
          <span>{dateAlerts.length} total</span>
          {aiSignalCount > 0 && <span className="text-accent">{aiSignalCount} AI signals</span>}
          {aiWaitCount > 0 && <span className="text-text-faint">{aiWaitCount} waits</span>}
          {ruleCount > 0 && <span>{ruleCount} rules</span>}
          {tookCount > 0 && <span className="text-bullish-text">{tookCount} took</span>}
          {skippedCount > 0 && <span>{skippedCount} skipped</span>}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <Filter className="h-3.5 w-3.5 text-text-faint" />

        {/* Source filter — AI Signals is the primary view (LONG/SHORT/RESISTANCE/EXIT) */}
        <div className="flex rounded-lg border border-border-subtle overflow-hidden">
          {([["all", "All"], ["ai", "AI Signals"], ["rules", "Rules"]] as const).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setSourceFilter(val)}
              className={`px-3 py-1 text-[11px] font-medium transition-colors ${
                sourceFilter === val
                  ? "bg-accent/15 text-accent"
                  : "text-text-muted hover:bg-surface-2"
              }`}
            >
              {val === "ai" && <Brain className="h-3 w-3 inline mr-1" />}
              {val === "rules" && <Crosshair className="h-3 w-3 inline mr-1" />}
              {label}
            </button>
          ))}
        </div>

        {/* Action filter */}
        <div className="flex rounded-lg border border-border-subtle overflow-hidden">
          {([["all", "All"], ["took", "Took"], ["skipped", "Skipped"], ["open", "Open"]] as const).map(([val, label]) => (
            <button
              key={val}
              onClick={() => setActionFilter(val)}
              className={`px-3 py-1 text-[11px] font-medium transition-colors ${
                actionFilter === val
                  ? "bg-accent/15 text-accent"
                  : "text-text-muted hover:bg-surface-2"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <span className="text-[10px] text-text-faint ml-auto">
          {filtered.length} result{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Alert List */}
      {isLoading ? (
        <div className="text-center py-12 text-text-muted text-sm">Loading alerts...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-text-muted text-sm space-y-2">
          <p>No replayable alerts match your filters.</p>
          {aiWaitCount > 0 && aiSignalCount === 0 && (
            <p className="text-[11px] text-text-faint">
              AI ran {aiWaitCount} scans today but found no actionable setups (all WAITs).
              Waits aren't replayed — AI was disciplined, not broken.
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-border-subtle bg-surface-1 overflow-hidden divide-y divide-border-subtle/30">
          {filtered.map((alert) => {
            const isAI = alert.alert_type?.startsWith("ai_");
            const time = new Date(alert.created_at).toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
            });
            const typeName = alert.alert_type?.replace(/_/g, " ") || "unknown";

            return (
              <div
                key={alert.id}
                className="px-4 py-3 flex items-center gap-3 hover:bg-surface-2/30 transition-colors group"
              >
                {/* Direction bar */}
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

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-text-primary">{alert.symbol}</span>
                    <span className="text-[11px] text-text-secondary truncate">{typeName}</span>
                    {isAI && (
                      <span className="text-[8px] font-bold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">
                        AI
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-text-faint mt-0.5">
                    <span>{time}</span>
                    <span>·</span>
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
                  </div>
                </div>

                {/* Direction badge */}
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

                {/* Action badge */}
                <div className="shrink-0 w-16 text-center">
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

                {/* Replay button */}
                <button
                  onClick={() => setReplayAlertId(alert.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-accent bg-accent/10 border border-accent/20 hover:bg-accent/20 opacity-70 group-hover:opacity-100 transition-all shrink-0"
                >
                  <Play className="h-3 w-3" />
                  Replay
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
