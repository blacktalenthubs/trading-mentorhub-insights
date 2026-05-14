import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

type SortKey = "time" | "symbol" | "direction" | "reason" | "entry" | "stop" | "t1" | "t2" | "rr" | "vol" | "cvd";
type SortDir = "asc" | "desc";

// Numeric columns default to descending (biggest first); string columns ascending.
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  time: "desc", symbol: "asc", direction: "asc", reason: "asc",
  entry: "desc", stop: "desc", t1: "desc", t2: "desc",
  rr: "desc", vol: "desc", cvd: "asc",
};

function rrNumeric(entry: number | null, stop: number | null, t1: number | null): number {
  if (entry === null || stop === null || t1 === null) return -Infinity;
  const risk = Math.abs(entry - stop);
  if (risk <= 0) return -Infinity;
  return Math.abs(t1 - entry) / risk;
}

export default function EODReportPage() {
  const { data: dates } = useAlertSessionDates();
  const [selectedDate, setSelectedDate] = useState("");
  const [dirFilter, setDirFilter] = useState<Filter>("All");
  const [symFilter, setSymFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const activeDate = selectedDate || dates?.[0] || "";
  const { data: alerts, isLoading } = useAlertsForDate(activeDate);

  function setSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(DEFAULT_DIR[key]);
    }
  }

  const rows = useMemo(() => {
    if (!alerts) return [];
    const filtered = alerts
      .filter((a) => dirFilter === "All" || a.direction === dirFilter)
      .filter((a) =>
        !symFilter ? true : a.symbol.toUpperCase().includes(symFilter.toUpperCase()),
      );

    const dir = sortDir === "asc" ? 1 : -1;
    const NEG_INF = -Number.MAX_VALUE;
    const sorted = [...filtered].sort((a, b) => {
      let va: number | string = "";
      let vb: number | string = "";
      switch (sortKey) {
        case "time":      va = a.created_at;            vb = b.created_at;            break;
        case "symbol":    va = a.symbol;                vb = b.symbol;                break;
        case "direction": va = a.direction;             vb = b.direction;             break;
        case "reason":    va = prettyReason(a.alert_type); vb = prettyReason(b.alert_type); break;
        case "entry":     va = a.entry ?? NEG_INF;      vb = b.entry ?? NEG_INF;      break;
        case "stop":      va = a.stop ?? NEG_INF;       vb = b.stop ?? NEG_INF;       break;
        case "t1":        va = a.target_1 ?? NEG_INF;   vb = b.target_1 ?? NEG_INF;   break;
        case "t2":        va = a.target_2 ?? NEG_INF;   vb = b.target_2 ?? NEG_INF;   break;
        case "rr":
          va = rrNumeric(a.entry ?? null, a.stop ?? null, a.target_1 ?? null);
          vb = rrNumeric(b.entry ?? null, b.stop ?? null, b.target_1 ?? null);
          break;
        case "vol":       va = a.volume_ratio ?? NEG_INF; vb = b.volume_ratio ?? NEG_INF; break;
        case "cvd":       va = a.cvd_diverging ?? -1;     vb = b.cvd_diverging ?? -1;     break;
      }
      if (va < vb) return -1 * dir;
      if (va > vb) return  1 * dir;
      return 0;
    });
    return sorted;
  }, [alerts, dirFilter, symFilter, sortKey, sortDir]);

  const counts = useMemo(() => {
    const c = { all: 0, BUY: 0, SHORT: 0, NOTICE: 0 } as Record<string, number>;
    (alerts || []).forEach((a) => {
      c.all += 1;
      c[a.direction] = (c[a.direction] || 0) + 1;
    });
    return c;
  }, [alerts]);

  const [copyStatus, setCopyStatus] = useState<"idle" | "ok" | "fail">("idle");
  const [shareStatus, setShareStatus] = useState<"idle" | "ok" | "fail">("idle");

  async function copyShareLink() {
    // Build a public URL the user can paste anywhere — matches the public
    // EOD report's route shape so the recipient lands on the same date.
    const base = window.location.origin;
    const url = activeDate ? `${base}/public/eod-report/${activeDate}` : `${base}/public/eod-report`;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setShareStatus("ok");
      setTimeout(() => setShareStatus("idle"), 2000);
    } catch {
      setShareStatus("fail");
      setTimeout(() => setShareStatus("idle"), 3000);
    }
  }

  async function copyAsTSV() {
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
    const text = [header.join("\t"), ...lines].join("\n");

    // Try modern clipboard API; fall back to textarea+execCommand on
    // browsers/contexts where it's unavailable (non-https, sandboxed iframe).
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        if (!ok) throw new Error("execCommand copy returned false");
      }
      setCopyStatus("ok");
      setTimeout(() => setCopyStatus("idle"), 2000);
    } catch (err) {
      console.error("Copy failed:", err);
      setCopyStatus("fail");
      setTimeout(() => setCopyStatus("idle"), 3000);
    }
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
        <div className="flex gap-2">
          <button
            onClick={copyShareLink}
            className={`rounded px-3 py-1.5 text-xs font-medium text-white transition ${
              shareStatus === "ok"   ? "bg-bullish hover:bg-bullish/90" :
              shareStatus === "fail" ? "bg-bearish-text" :
                                       "bg-accent hover:bg-accent-hover"
            }`}
            title="Copy a public, shareable link to this session's report"
          >
            {shareStatus === "ok"   ? "✓ Link copied" :
             shareStatus === "fail" ? "✗ Copy failed" :
                                      "🔗 Share public link"}
          </button>
          <button
            onClick={copyAsTSV}
            className={`rounded px-3 py-1.5 text-xs font-medium text-white transition ${
              copyStatus === "ok"   ? "bg-bullish hover:bg-bullish/90"     :
              copyStatus === "fail" ? "bg-bearish-text hover:bg-bearish-text/90" :
                                      "bg-accent hover:bg-accent-hover"
            }`}
            disabled={rows.length === 0}
            title="Copy as tab-separated values — paste into Sheets/Excel/Notion"
          >
            {copyStatus === "ok"   ? `✓ Copied ${rows.length} rows` :
             copyStatus === "fail" ? "✗ Copy failed"                :
                                     `Copy as TSV (${rows.length})`}
          </button>
        </div>
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
                  <SortableHeader  k="time"      label="Time"   align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="symbol"    label="Symbol" align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="direction" label="Dir"    align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="reason"    label="Reason" align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="entry"     label="Entry"  align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="stop"      label="Stop"   align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="t1"        label="T1"     align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="t2"        label="T2"     align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="rr"        label="R:R"    align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="vol"       label="Vol×"   align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <SortableHeader  k="cvd"       label="CVD"    align="center" sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                  <th className="px-3 py-2 text-center text-xs font-medium uppercase text-text-muted">Chart</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => {
                  const rr = rrRatio(a.entry ?? null, a.stop ?? null, a.target_1 ?? null);
                  const rrNum = parseFloat(rr);
                  return (
                    <tr key={a.id} className="border-b border-border-subtle/40 last:border-0 hover:bg-surface-3/40">
                      <td className="px-3 py-2 font-mono text-xs text-text-muted">{timeOnly(a.created_at)}</td>
                      <td className="px-3 py-2 font-semibold">
                        <button
                          onClick={() => setSymFilter(a.symbol)}
                          className="hover:text-accent hover:underline"
                          title={`Filter to just ${a.symbol}`}
                        >
                          {a.symbol}
                        </button>
                      </td>
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
                      <td className="px-3 py-2 text-center text-xs">
                        <Link
                          to={`/replay/${a.id}`}
                          className="rounded border border-border-subtle bg-surface-3 px-2 py-1 hover:border-accent hover:text-accent"
                          title="Open chart replay with entry/stop/T1/T2 overlay"
                        >
                          📈
                        </Link>
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
        Click any column header to sort.
      </p>
    </div>
  );
}

interface SortableHeaderProps {
  k: SortKey;
  label: string;
  align: "left" | "right" | "center";
  sortKey: SortKey;
  sortDir: SortDir;
  onSort: (k: SortKey) => void;
}

function SortableHeader({ k, label, align, sortKey, sortDir, onSort }: SortableHeaderProps) {
  const active = sortKey === k;
  const arrow = active ? (sortDir === "asc" ? "↑" : "↓") : "";
  const alignClass = align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th className={`px-3 py-2 font-medium ${alignClass}`}>
      <button
        onClick={() => onSort(k)}
        className={`inline-flex items-center gap-1 transition hover:text-text-primary ${
          active ? "text-accent" : ""
        }`}
        type="button"
      >
        {label}
        <span className="text-[10px] opacity-70">{arrow || "↕"}</span>
      </button>
    </th>
  );
}
