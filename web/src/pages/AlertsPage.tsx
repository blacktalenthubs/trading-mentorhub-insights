import { useState } from "react";
import {
  useAlertSessionDates,
  useAlertsForDate,
  useAlertSession,
  useAckAlert,
} from "../api/hooks";
import Badge from "../components/ui/Badge";
import Card from "../components/ui/Card";
import { useAuthStore } from "../stores/auth";

export default function AlertsPage() {
  const { data: dates } = useAlertSessionDates();
  const [selectedDate, setSelectedDate] = useState("");
  const [filter, setFilter] = useState("");
  const ackAlert = useAckAlert();

  const activeDate = selectedDate || dates?.[0] || "";
  const { data: alerts } = useAlertsForDate(activeDate);
  const { data: summary } = useAlertSession(activeDate);

  const filtered = alerts?.filter((a) => {
    if (!filter) return true;
    return a.symbol.includes(filter.toUpperCase()) || a.alert_type.includes(filter.toLowerCase());
  });

  async function handleDownloadPdf() {
    if (!activeDate) return;
    const token = useAuthStore.getState().accessToken;
    const res = await fetch(
      `/api/v1/alerts/pdf?start_date=${activeDate}&end_date=${activeDate}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `alerts_${activeDate}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Alerts</h1>
        <button
          onClick={handleDownloadPdf}
          className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
        >
          Export PDF
        </button>
      </div>

      {/* Date selector + filter */}
      <div className="flex flex-wrap gap-2">
        <select
          value={activeDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary"
        >
          {dates?.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter symbol/type..."
          className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
        />
      </div>

      {/* Session KPIs */}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <Card padding="sm">
            <p className="text-xs text-text-muted">Signals</p>
            <p className="mt-1 font-mono text-xl font-bold text-text-primary">{summary.total_alerts}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">BUY</p>
            <p className="mt-1 font-mono text-xl font-bold text-bullish-text">{summary.buy_alerts}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">SELL</p>
            <p className="mt-1 font-mono text-xl font-bold text-bearish-text">{summary.sell_alerts}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">T1</p>
            <p className="mt-1 font-mono text-xl font-bold text-bullish-text">{summary.target_1_hits}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">T2</p>
            <p className="mt-1 font-mono text-xl font-bold text-bullish-text">{summary.target_2_hits}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">Stopped</p>
            <p className="mt-1 font-mono text-xl font-bold text-bearish-text">{summary.stopped_out}</p>
          </Card>
          <Card padding="sm">
            <p className="text-xs text-text-muted">Active</p>
            <p className="mt-1 font-mono text-xl font-bold text-info-text">{summary.active_entries}</p>
          </Card>
        </div>
      )}

      {/* Alert list */}
      {filtered && filtered.length > 0 ? (
        <div className="space-y-2">
          {filtered.map((a) => (
            <div
              key={a.id}
              className="flex flex-col gap-2 rounded-lg border border-border-subtle bg-surface-2 px-4 py-3 shadow-card sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex items-center gap-3">
                <Badge variant={a.direction === "BUY" ? "bullish" : "bearish"}>
                  {a.direction}
                </Badge>
                <span className="font-medium text-text-primary">{a.symbol}</span>
                <span className="text-sm text-text-muted">{a.alert_type}</span>
                <span className="text-xs text-text-faint">{a.confidence}</span>
              </div>
              <div className="flex items-center gap-3 sm:text-right">
                <div>
                  <p className="font-mono text-sm font-medium text-text-primary">
                    ${a.price.toFixed(2)}
                  </p>
                  {a.entry && (
                    <p className="font-mono text-xs text-text-muted">
                      E: ${a.entry.toFixed(2)} S: ${a.stop?.toFixed(2)} T: ${a.target_1?.toFixed(2)}
                    </p>
                  )}
                  <p className="text-xs text-text-faint">{a.created_at}</p>
                </div>
                {/* ACK buttons */}
                {!a.user_action && a.direction === "BUY" && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => ackAlert.mutate({ id: a.id, action: "took" })}
                      className="rounded-lg bg-bullish-muted px-3 py-2 text-sm font-medium text-bullish-text hover:bg-bullish/20 active:scale-95"
                    >
                      Took
                    </button>
                    <button
                      onClick={() => ackAlert.mutate({ id: a.id, action: "skipped" })}
                      className="rounded-lg bg-surface-4 px-3 py-2 text-sm font-medium text-text-muted hover:bg-surface-3 active:scale-95"
                    >
                      Skip
                    </button>
                  </div>
                )}
                {a.user_action && (
                  <Badge variant={a.user_action === "took" ? "bullish" : "neutral"}>
                    {a.user_action}
                  </Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-text-faint">
          {activeDate ? "No alerts for this session" : "Select a session date"}
        </p>
      )}
    </div>
  );
}
