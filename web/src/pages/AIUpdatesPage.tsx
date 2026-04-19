import { useMemo, useState } from "react";
import { useAlertSessionDates, useAIUpdatesForDate } from "../api/hooks";
import Card from "../components/ui/Card";
import type { Alert } from "../types";

const ALL_SYMBOLS = ["SPY", "TSLA", "NVDA", "AMD", "META", "PLTR", "ETH-USD"];

function formatETTime(iso: string): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", {
      timeZone: "America/New_York",
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function groupBySymbol(alerts: Alert[]): Record<string, Alert[]> {
  const groups: Record<string, Alert[]> = {};
  for (const a of alerts) {
    if (!groups[a.symbol]) groups[a.symbol] = [];
    groups[a.symbol].push(a);
  }
  return groups;
}

function buildCSV(alerts: Alert[]): string {
  const header = ["date", "time_et", "symbol", "alert_type", "price", "message"];
  const rows = alerts.map((a) => [
    a.session_date,
    formatETTime(a.created_at),
    a.symbol,
    a.alert_type,
    a.price.toFixed(2),
    (a.message || "").replace(/"/g, '""').replace(/\r?\n/g, " "),
  ]);
  return [header, ...rows]
    .map((r) => r.map((cell) => `"${cell}"`).join(","))
    .join("\n");
}

export default function AIUpdatesPage() {
  const { data: dates } = useAlertSessionDates();
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);

  const activeDate = selectedDate || dates?.[0] || "";
  const { data: alerts, isLoading } = useAIUpdatesForDate(
    activeDate,
    selectedSymbols.length > 0 ? selectedSymbols : undefined,
  );

  const grouped = useMemo(() => groupBySymbol(alerts ?? []), [alerts]);
  const symbolsWithData = Object.keys(grouped).sort();
  const total = alerts?.length ?? 0;

  function toggleSymbol(sym: string) {
    setSelectedSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym],
    );
  }

  function handleExportCSV() {
    if (!alerts || alerts.length === 0) return;
    const csv = buildCSV(alerts);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ai_updates_${activeDate}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">AI Updates Report</h1>
          <p className="text-sm text-text-muted">
            Post-session audit of WAIT / RESISTANCE messages from the AI scanner.
          </p>
        </div>
        <button
          onClick={handleExportCSV}
          disabled={!alerts || alerts.length === 0}
          className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          Export CSV
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={activeDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary"
        >
          {dates?.map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <div className="flex flex-wrap gap-1.5">
          {ALL_SYMBOLS.map((sym) => {
            const active = selectedSymbols.includes(sym);
            return (
              <button
                key={sym}
                onClick={() => toggleSymbol(sym)}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
                  active
                    ? "border-accent bg-accent/20 text-accent"
                    : "border-border-subtle bg-surface-3 text-text-muted hover:text-text-primary"
                }`}
              >
                {sym}
              </button>
            );
          })}
          {selectedSymbols.length > 0 && (
            <button
              onClick={() => setSelectedSymbols([])}
              className="rounded-full border border-border-subtle bg-surface-3 px-2.5 py-1 text-xs font-medium text-text-muted hover:text-text-primary"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      <Card padding="sm">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="text-text-primary">
            <span className="font-semibold">{total}</span> total updates
          </span>
          {symbolsWithData.map((sym) => (
            <span key={sym} className="text-text-muted">
              {sym}: <span className="text-text-primary">{grouped[sym].length}</span>
            </span>
          ))}
        </div>
      </Card>

      {isLoading && <p className="text-sm text-text-muted">Loading...</p>}

      {!isLoading && total === 0 && (
        <Card padding="md">
          <p className="text-sm text-text-muted">
            No AI updates for {activeDate || "this date"}
            {selectedSymbols.length > 0 ? ` in ${selectedSymbols.join(", ")}` : ""}.
          </p>
        </Card>
      )}

      {symbolsWithData.map((sym) => (
        <Card key={sym} padding="md">
          <div className="mb-3 flex items-center justify-between border-b border-border-subtle pb-2">
            <h2 className="font-display text-lg font-bold">{sym}</h2>
            <span className="text-xs text-text-muted">
              {grouped[sym].length} update{grouped[sym].length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="space-y-1.5">
            {grouped[sym].map((a) => (
              <div
                key={a.id}
                className="flex flex-col gap-1 rounded border border-border-subtle/40 bg-surface-1 px-2.5 py-1.5 sm:flex-row sm:items-baseline sm:gap-3"
              >
                <span className="font-mono text-xs text-text-muted shrink-0">
                  {formatETTime(a.created_at)}
                </span>
                <span className="font-mono text-xs text-text-primary shrink-0">
                  ${a.price.toFixed(2)}
                </span>
                <span className="text-xs text-text-secondary break-words">
                  {a.message || <em className="text-text-muted">(no message)</em>}
                </span>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
