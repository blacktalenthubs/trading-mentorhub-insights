import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAlertSessionDates, useAlertsForDate } from "../api/hooks";
import Badge from "../components/ui/Badge";
import EmptyState from "../components/ui/EmptyState";
import { Filter as FilterIcon } from "lucide-react";

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
  t = t.replace(/^staged_pwh_break$/, "PWH break ↑");
  t = t.replace(/^staged_pwl_reclaim$/, "PWL reclaim ↑");
  t = t.replace(/^staged_pwh_rejection$/, "PWH reject");
  t = t.replace(/^staged_pwl_break$/, "PWL break");
  t = t.replace(/^staged_pmh_break$/, "PMH break ↑");
  t = t.replace(/^staged_pml_reclaim$/, "PML reclaim ↑");
  t = t.replace(/^staged_pmh_rejection$/, "PMH reject");
  t = t.replace(/^staged_pml_break$/, "PML break");
  t = t.replace(/^pwh_held$/, "PWH held ✓");
  t = t.replace(/^pwh_wick_reclaim$/, "PWH wick reclaim ↑");
  t = t.replace(/^pwl_held$/, "PWL held ✓");
  t = t.replace(/^pwl_wick_reclaim$/, "PWL wick reclaim ↑");
  t = t.replace(/^pmh_held$/, "PMH held ✓");
  t = t.replace(/^pmh_wick_reclaim$/, "PMH wick reclaim ↑");
  t = t.replace(/^pml_held$/, "PML held ✓");
  t = t.replace(/^pml_wick_reclaim$/, "PML wick reclaim ↑");
  t = t.replace(/^htf_proximity_pwh$/, "Near PWH ⚠️");
  t = t.replace(/^htf_proximity_pwl$/, "Near PWL ⚠️");
  t = t.replace(/^htf_proximity_pmh$/, "Near PMH ⚠️");
  t = t.replace(/^htf_proximity_pml$/, "Near PML ⚠️");
  t = t.replace(/^vwap_reclaim_long$/, "VWAP reclaim");
  t = t.replace(/^vwap_reject_short$/, "VWAP reject");
  t = t.replace(/^open_reclaimed$/, "Open reclaim ↑");
  t = t.replace(/^open_wick_reclaim$/, "Open wick reclaim ↑");
  t = t.replace(/^open_held$/, "Open held ✓");
  t = t.replace(/^open_support_hold$/, "Open support hold ✓");
  t = t.replace(/^open_lost$/, "Open lost ↓");
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
  // Backend timestamps are UTC, returned as naive strings either
  // "2026-05-11 14:35:04.012345" (Postgres) or ISO 8601 without 'Z'.
  // Normalize to UTC-suffixed ISO so Date() parses correctly, then
  // render in America/New_York (US market clock).
  const normalized = iso.includes("T")
    ? (iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z")
    : iso.replace(" ", "T") + "Z";
  const d = new Date(normalized);
  if (isNaN(d.getTime())) {
    const t = iso.includes("T") ? iso.split("T")[1] : (iso.split(" ")[1] || iso);
    return t.slice(0, 5);
  }
  return d.toLocaleTimeString("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function rrRatio(entry: number | null, stop: number | null, t1: number | null): string {
  if (entry === null || stop === null || t1 === null) return "—";
  const risk = Math.abs(entry - stop);
  if (risk <= 0) return "—";
  return (Math.abs(t1 - entry) / risk).toFixed(1);
}

// NOTICE alerts excluded — report focuses on actionable BUY/SHORT only.
const DIRECTION_FILTERS = ["All", "BUY", "SHORT"] as const;
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
  const [view, setView] = useState<"delivered" | "notrouted">("delivered");

  const activeDate = selectedDate || dates?.[0] || "";
  const { data: rawAlerts, isLoading } = useAlertsForDate(activeDate);
  // Two review buckets (merged muted into not-routed 2026-06-17): Delivered (fired)
  // vs Not-routed (everything held back — gate catches AND muted/disabled types).
  // Each row keeps its own reason. confluence_collapsed (same-moment dup) stays out.
  const buckets = useMemo(() => {
    const all = rawAlerts || [];
    return {
      delivered: all.filter((a) => !a.suppressed_reason),
      notrouted: all.filter(
        (a) =>
          !!a.suppressed_reason &&
          !a.suppressed_reason.startsWith("confluence_collapsed"),
      ),
    };
  }, [rawAlerts]);
  const alerts = buckets[view];

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
      // Drop NOTICE alerts entirely — report focuses on BUY/SHORT.
      .filter((a) => a.direction !== "NOTICE")
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
    const c = { all: 0, BUY: 0, SHORT: 0 } as Record<string, number>;
    (alerts || [])
      .filter((a) => a.direction !== "NOTICE")
      .forEach((a) => {
        c.all += 1;
        c[a.direction] = (c[a.direction] || 0) + 1;
      });
    return c;
  }, [alerts]);

  // Headline stats for the summary banner.
  const stats = useMemo(() => {
    const actionable = (alerts || []).filter((a) => a.direction !== "NOTICE");
    const rrVals: number[] = [];
    let topRR = 0;
    let topRRSymbol = "";
    let topVol = 0;
    let topVolSymbol = "";
    for (const a of actionable) {
      const rr = rrNumeric(a.entry ?? null, a.stop ?? null, a.target_1 ?? null);
      if (Number.isFinite(rr)) {
        rrVals.push(rr);
        if (rr > topRR) { topRR = rr; topRRSymbol = a.symbol; }
      }
      if (a.volume_ratio != null && a.volume_ratio > topVol) {
        topVol = a.volume_ratio; topVolSymbol = a.symbol;
      }
    }
    return {
      total: actionable.length,
      buys: actionable.filter((a) => a.direction === "BUY").length,
      shorts: actionable.filter((a) => a.direction === "SHORT").length,
      symbols: new Set(actionable.map((a) => a.symbol)).size,
      topRR,
      topRRSymbol,
      topVol,
      topVolSymbol,
    };
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
    <div className="space-y-5">
      {/* Hero + stats */}
      <div className="relative overflow-hidden rounded-2xl border border-border-subtle bg-gradient-to-br from-accent/10 via-surface-1 to-bullish/5 p-5">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.06),transparent_60%)]" />
        <div className="relative flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl font-bold">EOD Report</h1>
            <p className="mt-0.5 text-sm text-text-muted">
              Every alert fired this session — entry, levels, and rule that triggered.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={copyShareLink}
              className={`rounded-lg px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition ${
                shareStatus === "ok"   ? "bg-bullish hover:bg-bullish/90" :
                shareStatus === "fail" ? "bg-rose-500" :
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
              className={`rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-xs font-semibold text-text-primary shadow-sm transition hover:border-accent hover:text-accent ${
                copyStatus === "ok"   ? "border-bullish text-bullish" :
                copyStatus === "fail" ? "border-rose-400 text-rose-400" : ""
              }`}
              disabled={rows.length === 0}
              title="Copy as tab-separated values — paste into Sheets/Excel/Notion"
            >
              {copyStatus === "ok"   ? `✓ Copied ${rows.length} rows` :
               copyStatus === "fail" ? "✗ Copy failed"                :
                                       `Copy TSV (${rows.length})`}
            </button>
          </div>
        </div>

        {/* Stats summary */}
        <div className="relative mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatTile label="Alerts fired" value={String(stats.total)} accent="text-text-primary" />
          <StatTile label="Long signals" value={String(stats.buys)}  accent="text-bullish-text" />
          <StatTile label="Short signals" value={String(stats.shorts)} accent="text-rose-400" />
          <StatTile
            label={stats.topRRSymbol ? `Best R:R · ${stats.topRRSymbol}` : "Best R:R"}
            value={stats.topRR ? stats.topRR.toFixed(1) : "—"}
            accent="text-emerald-400"
          />
          <StatTile
            label={stats.topVolSymbol ? `Top Vol× · ${stats.topVolSymbol}` : "Top Vol×"}
            value={stats.topVol ? `${stats.topVol.toFixed(2)}×` : "—"}
            accent="text-amber-400"
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Review bucket — delivered vs what was held back */}
        <div className="flex gap-1 rounded-lg border border-border-subtle bg-surface-2 p-1">
          {([
            { key: "delivered", label: "Delivered", count: buckets.delivered.length, active: "bg-accent/20 text-accent" },
            { key: "notrouted", label: "Not-routed", count: buckets.notrouted.length, active: "bg-amber-500/20 text-amber-300" },
          ] as const).map((t) => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                view === t.key ? `${t.active} shadow-inner` : "text-text-muted hover:text-text-primary"
              }`}
            >
              {t.label}
              <span className="ml-1.5 opacity-75">{t.count}</span>
            </button>
          ))}
        </div>

        <select
          value={activeDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-sm text-text-primary shadow-sm transition hover:border-border-strong focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        >
          {(dates || []).map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <input
          type="text"
          value={symFilter}
          onChange={(e) => setSymFilter(e.target.value)}
          placeholder="🔍 Filter symbol..."
          className="rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-sm text-text-primary shadow-sm transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />

        <div className="flex gap-1 rounded-lg border border-border-subtle bg-surface-2 p-1">
          {DIRECTION_FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setDirFilter(f)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                dirFilter === f
                  ? f === "BUY"   ? "bg-bullish-text/20 text-bullish-text shadow-inner"
                  : f === "SHORT" ? "bg-rose-500/20 text-rose-300 shadow-inner"
                  :                 "bg-accent/20 text-accent shadow-inner"
                  : "text-text-muted hover:text-text-primary"
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

      <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-1 shadow-xl shadow-black/20">
        {isLoading ? (
          <p className="p-6 text-sm text-text-muted">Loading…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            icon={FilterIcon}
            title="No alerts match your filters"
            hint={symFilter || dirFilter !== "All"
              ? "Your symbol or direction filter hid every alert. Clear filters to see the full session."
              : "The scanner didn't fire any alerts on this date."}
            primary={(symFilter || dirFilter !== "All") ? { label: "Clear filters", onClick: () => { setSymFilter(""); setDirFilter("All"); } } : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border-subtle bg-surface-2 text-left text-[11px] uppercase tracking-wider text-text-muted">
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
                  <th className="px-3 py-3 text-center font-medium">Chart</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a, i) => {
                  const rr = rrRatio(a.entry ?? null, a.stop ?? null, a.target_1 ?? null);
                  const rrNum = parseFloat(rr);
                  const zebra = i % 2 === 0 ? "bg-surface-1" : "bg-surface-1/40";
                  return (
                    <tr key={a.id} className={`${zebra} border-b border-border-subtle/30 last:border-0 transition hover:bg-accent/5`}>
                      <td className="px-3 py-2.5 font-mono text-xs text-text-muted">{timeOnly(a.created_at)}</td>
                      <td className="px-3 py-2.5 font-bold tracking-wide">
                        <button
                          onClick={() => setSymFilter(a.symbol)}
                          className="text-text-primary transition hover:text-accent hover:underline"
                          title={`Filter to just ${a.symbol}`}
                        >
                          {a.symbol}
                        </button>
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge variant={
                          a.direction === "BUY" || a.direction === "LONG" ? "bullish" :
                          a.direction === "SHORT" ? "bearish" :
                          a.direction === "NOTICE" ? "info" : "neutral"
                        }>
                          {a.direction}
                        </Badge>
                      </td>
                      <td className="px-3 py-2.5 text-text-secondary">{prettyReason(a.alert_type)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-text-primary">{formatPrice(a.entry)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-rose-400">{formatPrice(a.stop)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-emerald-400">{formatPrice(a.target_1)}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-xs text-emerald-400/80">{formatPrice(a.target_2)}</td>
                      <td className={`px-3 py-2.5 text-right font-mono text-xs font-bold ${
                        rr === "—" ? "text-text-muted" :
                        rrNum >= 3 ? "text-emerald-400" :
                        rrNum >= 1.5 ? "text-amber-400" : "text-rose-400"
                      }`}>{rr}</td>
                      <td className={`px-3 py-2.5 text-right font-mono text-xs font-semibold ${
                        a.volume_ratio == null ? "text-text-muted" :
                        a.volume_ratio >= 2.0 ? "text-emerald-400" :
                        a.volume_ratio < 1.0 ? "text-rose-400" : "text-amber-400"
                      }`}>{a.volume_ratio != null ? `${a.volume_ratio.toFixed(2)}×` : "—"}</td>
                      <td className="px-3 py-2.5 text-center text-xs">
                        {a.cvd_diverging == null ? (
                          <span className="text-text-muted">—</span>
                        ) : a.cvd_diverging ? (
                          <span className="text-rose-400" title="CVD diverging — order flow not confirming">⚠ diverge</span>
                        ) : (
                          <span className="text-emerald-400" title="CVD confirming">✓ confirm</span>
                        )}
                      </td>
                      <td className="px-3 py-2.5 text-center text-xs">
                        <Link
                          to={`/replay/${a.id}`}
                          className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-3 px-2.5 py-1 font-medium text-text-secondary transition hover:border-accent hover:bg-accent/10 hover:text-accent"
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
      </div>

      <div className="rounded-lg border border-border-subtle/50 bg-surface-1/40 p-4 text-xs leading-relaxed text-text-muted">
        <p className="mb-2 font-semibold uppercase tracking-wider text-text-secondary">Legend</p>
        <ul className="space-y-1">
          <li><span className="font-medium text-text-secondary">R:R</span> — reward-to-risk against T1 (<span className="text-emerald-400">green ≥ 3</span>, <span className="text-amber-400">amber 1.5–3</span>, <span className="text-rose-400">red &lt; 1.5</span>)</li>
          <li><span className="font-medium text-text-secondary">Vol×</span> — fire-bar volume vs average (<span className="text-emerald-400">green ≥ 2.0×</span>, <span className="text-amber-400">amber 1.0–2.0×</span>, <span className="text-rose-400">red &lt; 1.0×</span>)</li>
          <li><span className="font-medium text-text-secondary">CVD</span> — order-flow alignment (<span className="text-emerald-400">✓ confirm</span> = price &amp; flow agree, <span className="text-rose-400">⚠ diverge</span> = price moving but flow not)</li>
          <li>Click any column header to sort · Click a symbol cell to filter to just that ticker · Click <span className="text-accent">📈</span> for the chart replay</li>
        </ul>
      </div>
    </div>
  );
}

function StatTile({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1/60 px-4 py-3 backdrop-blur-sm transition hover:border-border-strong hover:bg-surface-1/80">
      <div className={`font-mono text-2xl font-bold leading-tight ${accent}`}>{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
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
