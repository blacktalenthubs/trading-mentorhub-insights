import { useMemo, useState } from "react";
import { useAlertSessionDates, useAlertsForDate } from "../api/hooks";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";

// Turn raw rule tag into a short human label for the Reason column.
function prettyReason(alertType: string | null | undefined): string {
  if (!alertType) return "—";
  let t = alertType.replace(/^tv_/, "");
  t = t.replace(/^ma_bounce_long_v3_/, "MA bounce ");
  t = t.replace(/^ma_rejection_short_v3_/, "MA rejection ");
  t = t.replace(/^ma_proximity_long_v3_/, "MA proximity ↑ ");
  t = t.replace(/^ma_proximity_short_v3_/, "MA proximity ↓ ");
  t = t.replace(/^staged_pdh_break$/, "PDH break");
  t = t.replace(/^staged_pdl_reclaim$/, "PDL reclaim");
  t = t.replace(/^staged_pdh_rejection$/, "PDH reject");
  t = t.replace(/^staged_pdh_failed_short$/, "PDH fail-short");
  t = t.replace(/^staged_pdl_break$/, "PDL break");
  t = t.replace(/^pivot_aligned_break_long$/, "1h/4h pivot break ↑");
  t = t.replace(/^pivot_aligned_break_short$/, "1h/4h pivot break ↓");
  t = t.replace(/^pivot_aligned_reclaim_long$/, "1h/4h pivot reclaim ↑");
  t = t.replace(/^pivot_aligned_reject_short$/, "1h/4h pivot reject ↓");
  t = t.replace(/^vwap_reclaim_long$/, "VWAP reclaim");
  t = t.replace(/^vwap_reject_short$/, "VWAP reject");
  t = t.replace(/ema(\d+)_ema(\d+)/g, "EMA$1+EMA$2");
  t = t.replace(/ema(\d+)/g, "EMA$1");
  return t.replace(/_/g, " ");
}

function formatPrice(p: number | null | undefined): string {
  if (p === null || p === undefined) return "—";
  return `$${p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function timeOnly(iso: string): string {
  if (!iso) return "";
  // Backend returns "2026-05-11 14:35:04.012345" or ISO 8601
  const t = iso.includes("T") ? iso.split("T")[1] : (iso.split(" ")[1] || iso);
  return t.slice(0, 5);
}

function rrRatio(entry: number | null, stop: number | null, t1: number | null): string {
  if (entry === null || stop === null || t1 === null) return "—";
  const risk = Math.abs(entry - stop);
  if (risk <= 0) return "—";
  return (Math.abs(t1 - entry) / risk).toFixed(1);
}

const DIRECTION_FILTERS = ["All", "BUY", "SHORT", "NOTICE"] as const;
type Filter = (typeof DIRECTION_FILTERS)[number];

export default function EODReportPage() {
  const { data: dates } = useAlertSessionDates();
  const [selectedDate, setSelectedDate] = useState("");
  const [dirFilter, setDirFilter] = useState<Filter>("All");
  const [symFilter, setSymFilter] = useState("");

  const activeDate = selectedDate || dates?.[0] || "";
  const { data: alerts, isLoading } = useAlertsForDate(activeDate);

  const rows = useMemo(() => {
    if (!alerts) return [];
    return alerts
      .filter((a) => dirFilter === "All" || a.direction === dirFilter)
      .filter((a) =>
        !symFilter ? true : a.symbol.toUpperCase().includes(symFilter.toUpperCase()),
      );
  }, [alerts, dirFilter, symFilter]);

  const counts = useMemo(() => {
    const c = { all: 0, BUY: 0, SHORT: 0, NOTICE: 0 } as Record<string, number>;
    (alerts || []).forEach((a) => {
      c.all += 1;
      c[a.direction] = (c[a.direction] || 0) + 1;
    });
    return c;
  }, [alerts]);

  function copyAsTSV() {
    const header = ["Time", "Symbol", "Direction", "Reason", "Entry", "Stop", "T1", "T2", "R:R", "Vol×", "CVD"];
    const lines = rows.map((a) => [
      timeOnly(a.created_at),
      a.symbol,
      a.direction,
      prettyReason(a.alert_type),
      a.entry?.toFixed(2) ?? "",
      a.stop?.toFixed(2) ?? "",
      a.target_1?.toFixed(2) ?? "",
      a.target_2?.toFixed(2) ?? "",
      rrRatio(a.entry ?? null, a.stop ?? null, a.target_1 ?? null),
      a.volume_ratio != null ? a.volume_ratio.toFixed(2) : "",
      a.cvd_diverging == null ? "" : a.cvd_diverging ? "diverging" : "confirming",
    ].join("\t"));
    navigator.clipboard.writeText([header.join("\t"), ...lines].join("\n"));
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">EOD Report</h1>
          <p className="text-sm text-text-muted">
            Full review of every alert fired in the selected session — entry, levels, and rule that triggered.
          </p>
        </div>
        <button
          onClick={copyAsTSV}
          className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover"
          disabled={rows.length === 0}
          title="Copy as tab-separated values — paste into Sheets/Excel/Notion"
        >
          Copy as TSV
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={activeDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary"
        >
          {(dates || []).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <input
          type="text"
          value={symFilter}
          onChange={(e) => setSymFilter(e.target.value)}
          placeholder="Filter symbol..."
          className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
        />

        <div className="flex gap-1">
          {DIRECTION_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setDirFilter(f)}
              className={`rounded px-3 py-1.5 text-xs font-medium transition ${
                dirFilter === f
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted hover:text-text-primary"
              }`}
            >
              {f}
              <span className="ml-1.5 opacity-75">
                {f === "All" ? counts.all : counts[f] || 0}
              </span>
            </button>
          ))}
        </div>
      </div>

      <Card>
        {isLoading ? (
          <p className="p-4 text-sm text-text-muted">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="p-4 text-sm text-text-muted">No alerts in this session matching your filters.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border-subtle text-left text-xs uppercase text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Symbol</th>
                  <th className="px-3 py-2 font-medium">Dir</th>
                  <th className="px-3 py-2 font-medium">Reason</th>
                  <th className="px-3 py-2 text-right font-medium">Entry</th>
                  <th className="px-3 py-2 text-right font-medium">Stop</th>
                  <th className="px-3 py-2 text-right font-medium">T1</th>
                  <th className="px-3 py-2 text-right font-medium">T2</th>
                  <th className="px-3 py-2 text-right font-medium">R:R</th>
                  <th className="px-3 py-2 text-right font-medium">Vol×</th>
                  <th className="px-3 py-2 text-center font-medium">CVD</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => {
                  const rr = rrRatio(a.entry ?? null, a.stop ?? null, a.target_1 ?? null);
                  const rrNum = parseFloat(rr);
                  return (
                    <tr key={a.id} className="border-b border-border-subtle/40 last:border-0 hover:bg-surface-3/40">
                      <td className="px-3 py-2 font-mono text-xs text-text-muted">{timeOnly(a.created_at)}</td>
                      <td className="px-3 py-2 font-semibold">{a.symbol}</td>
                      <td className="px-3 py-2">
                        <Badge variant={
                          a.direction === "BUY" || a.direction === "LONG" ? "bullish" :
                          a.direction === "SHORT" ? "bearish" :
                          a.direction === "NOTICE" ? "info" : "neutral"
                        }>
                          {a.direction}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-text-secondary">{prettyReason(a.alert_type)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs">{formatPrice(a.entry)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-rose-400">{formatPrice(a.stop)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-emerald-400">{formatPrice(a.target_1)}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-emerald-400/80">{formatPrice(a.target_2)}</td>
                      <td className={`px-3 py-2 text-right font-mono text-xs font-semibold ${
                        rr === "—" ? "text-text-muted" :
                        rrNum >= 3 ? "text-emerald-400" :
                        rrNum >= 1.5 ? "text-amber-400" : "text-rose-400"
                      }`}>{rr}</td>
                      <td className={`px-3 py-2 text-right font-mono text-xs ${
                        a.volume_ratio == null ? "text-text-muted" :
                        a.volume_ratio >= 2.0 ? "text-emerald-400" :
                        a.volume_ratio < 1.0 ? "text-rose-400" : "text-amber-400"
                      }`}>{a.volume_ratio != null ? `${a.volume_ratio.toFixed(2)}×` : "—"}</td>
                      <td className="px-3 py-2 text-center text-xs">
                        {a.cvd_diverging == null ? (
                          <span className="text-text-muted">—</span>
                        ) : a.cvd_diverging ? (
                          <span className="text-rose-400" title="CVD diverging — order flow not confirming">⚠ diverge</span>
                        ) : (
                          <span className="text-emerald-400" title="CVD confirming">✓ confirm</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <p className="text-xs text-text-muted">
        Tip: <span className="font-medium">R:R</span> is reward-to-risk against T1 (green ≥ 3, amber 1.5–3, red &lt; 1.5).
        <span className="font-medium"> Vol×</span> is fire-bar volume vs avg (green ≥ 2.0×, amber 1.0–2.0×, red &lt; 1.0×).
        <span className="font-medium"> CVD</span> = order flow alignment (✓ confirm = price & flow agree, ⚠ diverge = price moving but flow not).
      </p>
    </div>
  );
}
