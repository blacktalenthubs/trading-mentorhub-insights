/** Public EOD Report — shareable, unauthenticated view of the day's alerts.
 *
 *  URL: /public/eod-report  or  /public/eod-report/:date  or
 *       /public/eod-report/:date/:symbol  (per-stock review)
 *
 *  Mirrors the authenticated EODReportPage layout but uses /public/eod-report/*
 *  backend endpoints (admin user's alerts, no auth required). Each row links
 *  to /replay/:alertId (also public) for the per-alert chart view with
 *  entry/stop/T1/T2 overlays.
 */

import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import Badge from "../components/ui/Badge";
import type { Alert } from "../types";

function usePublicSessionDates() {
  return useQuery({
    queryKey: ["public-session-dates"],
    queryFn: () => api.get<string[]>("/public/eod-report/session-dates"),
  });
}

function usePublicAlerts(date: string, symbol?: string) {
  return useQuery({
    queryKey: ["public-alerts", date, symbol || ""],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (date) qs.set("date", date);
      if (symbol) qs.set("symbol", symbol);
      const path = qs.toString()
        ? `/public/eod-report/alerts?${qs.toString()}`
        : "/public/eod-report/alerts";
      return api.get<Alert[]>(path);
    },
    enabled: true,
  });
}

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
  t = t.replace(/^open_reclaimed$/, "Open reclaim ↑");
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
  const t = iso.includes("T") ? iso.split("T")[1] : (iso.split(" ")[1] || iso);
  return t.slice(0, 5);
}

function rrRatio(entry: number | null, stop: number | null, t1: number | null): string {
  if (entry === null || stop === null || t1 === null) return "—";
  const risk = Math.abs(entry - stop);
  if (risk <= 0) return "—";
  return (Math.abs(t1 - entry) / risk).toFixed(1);
}

// NOTICE alerts excluded from public report (informational, less actionable).
const DIRECTION_FILTERS = ["All", "BUY", "SHORT"] as const;
type Filter = (typeof DIRECTION_FILTERS)[number];

type SortKey = "time" | "symbol" | "direction" | "reason" | "entry" | "stop" | "t1" | "t2" | "rr" | "vol";
type SortDir = "asc" | "desc";

// Numeric columns default to descending (biggest first); string columns ascending.
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  time: "desc", symbol: "asc", direction: "asc", reason: "asc",
  entry: "desc", stop: "desc", t1: "desc", t2: "desc",
  rr: "desc", vol: "desc",
};

function rrNumeric(entry: number | null, stop: number | null, t1: number | null): number {
  if (entry === null || stop === null || t1 === null) return -Infinity;
  const risk = Math.abs(entry - stop);
  if (risk <= 0) return -Infinity;
  return Math.abs(t1 - entry) / risk;
}

export default function PublicEODReportPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { date: dateParam, symbol: symbolParam } = useParams<{ date?: string; symbol?: string }>();
  const { data: dates } = usePublicSessionDates();

  // Detect base path so the same component works mounted at /track-record
  // (replaces the old auto-pilot view) AND /public/eod-report. Date / symbol
  // route params follow the base path's segments.
  const basePath = location.pathname.startsWith("/track-record")
    ? "/track-record"
    : "/public/eod-report";

  // If a date is in the URL, use it; otherwise pick the latest available
  const activeDate = dateParam || dates?.[0] || "";
  const focusSymbol = symbolParam ? symbolParam.toUpperCase() : undefined;

  const { data: alerts, isLoading } = usePublicAlerts(activeDate, focusSymbol);
  const [dirFilter, setDirFilter] = useState<Filter>("All");
  const [symFilter, setSymFilter] = useState("");
  const [shareStatus, setShareStatus] = useState<"idle" | "ok" | "fail">("idle");
  const [sortKey, setSortKey] = useState<SortKey>("time");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function setSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(DEFAULT_DIR[key]);
    }
  }

  // Sync browser back/forward with date param: navigating to {basePath}/X
  // updates activeDate via the route. Changing the date dropdown navigates.
  function selectDate(d: string) {
    if (focusSymbol) navigate(`${basePath}/${d}/${focusSymbol}`);
    else navigate(`${basePath}/${d}`);
  }

  async function copyShareLink() {
    const url = window.location.href;
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

  // Reset symbol typing filter when route symbol changes (per-stock view)
  useEffect(() => { setSymFilter(""); }, [focusSymbol]);

  const rows = useMemo(() => {
    if (!alerts) return [];
    const filtered = alerts
      // Drop NOTICE alerts entirely — public report shows actionable BUY/SHORT only.
      .filter((a) => a.direction !== "NOTICE")
      .filter((a) => dirFilter === "All" || a.direction === dirFilter)
      .filter((a) =>
        !symFilter ? true : a.symbol.toUpperCase().includes(symFilter.toUpperCase()),
      );

    const dir = sortDir === "asc" ? 1 : -1;
    const NEG_INF = -Number.MAX_VALUE;
    return [...filtered].sort((a, b) => {
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
      }
      if (va < vb) return -1 * dir;
      if (va > vb) return  1 * dir;
      return 0;
    });
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
    const volVals: number[] = [];
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
      if (a.volume_ratio != null) {
        volVals.push(a.volume_ratio);
        if (a.volume_ratio > topVol) { topVol = a.volume_ratio; topVolSymbol = a.symbol; }
      }
    }
    const avg = (xs: number[]) => xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : 0;
    return {
      total: actionable.length,
      buys: actionable.filter((a) => a.direction === "BUY").length,
      shorts: actionable.filter((a) => a.direction === "SHORT").length,
      symbols: new Set(actionable.map((a) => a.symbol)).size,
      avgRR: avg(rrVals),
      topRR,
      topRRSymbol,
      avgVol: avg(volVals),
      topVol,
      topVolSymbol,
    };
  }, [alerts]);

  // Unique symbols in the day's stream — used as the per-stock review jump list
  const symbolList = useMemo(() => {
    const set = new Set<string>();
    (alerts || []).forEach((a) => set.add(a.symbol));
    return Array.from(set).sort();
  }, [alerts]);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      {/* Public hero — gradient + stats banner */}
      <div className="relative overflow-hidden border-b border-border-subtle bg-gradient-to-br from-accent/15 via-surface-1 to-bullish/10">
        {/* Subtle radial glow for depth */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.08),transparent_60%),radial-gradient(circle_at_bottom_left,rgba(59,130,246,0.08),transparent_55%)]" />

        <div className="relative mx-auto max-w-7xl px-6 py-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-text-muted">
                <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-bullish-text shadow-[0_0_8px_rgba(34,197,94,0.7)]" />
                Public · Live trade signals
              </div>
              <h1 className="mt-2 font-display text-3xl font-bold leading-tight sm:text-4xl">
                TradingWithAI <span className="text-text-muted">—</span> EOD Alert Report
                {focusSymbol && (
                  <span className="ml-3 inline-block rounded-md bg-accent/20 px-2.5 py-1 align-middle text-base font-semibold text-accent">
                    {focusSymbol}
                  </span>
                )}
              </h1>
              <p className="mt-1 max-w-2xl text-sm text-text-muted">
                {focusSymbol
                  ? `Every alert that fired for ${focusSymbol} on this session — entry, stop, targets, and the rule that triggered.`
                  : "Every signal our Pine indicators fired this session. Click any row for the chart replay with our levels overlaid."}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={copyShareLink}
                className={`rounded-lg px-3.5 py-2 text-xs font-semibold text-white transition shadow-lg shadow-accent/20 ${
                  shareStatus === "ok"   ? "bg-bullish hover:bg-bullish/90" :
                  shareStatus === "fail" ? "bg-bearish-text" :
                                            "bg-accent hover:bg-accent-hover"
                }`}
                title="Copy this page's URL to share"
              >
                {shareStatus === "ok"   ? "✓ Link copied" :
                 shareStatus === "fail" ? "✗ Copy failed" :
                                           "🔗 Copy share link"}
              </button>
              <Link
                to="/register"
                className="rounded-lg bg-bullish px-3.5 py-2 text-xs font-semibold text-white shadow-lg shadow-bullish/30 transition hover:bg-bullish/90 hover:shadow-bullish/40"
              >
                Get live alerts →
              </Link>
            </div>
          </div>

          {/* Stats summary */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <StatTile label="Alerts fired" value={String(stats.total)} accent="text-text-primary" />
            <StatTile label="Long signals"  value={String(stats.buys)}    accent="text-bullish-text" />
            <StatTile label="Short signals" value={String(stats.shorts)}  accent="text-rose-400" />
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
      </div>

      <div className="mx-auto max-w-7xl space-y-4 p-6">
        {/* Date + filters */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={activeDate}
            onChange={(e) => selectDate(e.target.value)}
            className="rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-sm text-text-primary shadow-sm transition hover:border-border-strong focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          >
            {(dates || []).map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>

          {!focusSymbol && (
            <input
              type="text"
              value={symFilter}
              onChange={(e) => setSymFilter(e.target.value)}
              placeholder="🔍 Filter symbol..."
              className="rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-sm text-text-primary shadow-sm transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            />
          )}

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

          {focusSymbol && (
            <Link
              to={`${basePath}/${activeDate}`}
              className="ml-auto rounded-lg border border-border-subtle bg-surface-2 px-3.5 py-2 text-xs font-medium text-text-muted shadow-sm transition hover:border-accent hover:text-accent"
            >
              ← Back to all symbols
            </Link>
          )}
        </div>

        {/* Per-stock jump list (only on the full session view) */}
        {!focusSymbol && symbolList.length > 0 && (
          <div className="rounded-xl border border-border-subtle bg-surface-1/60 p-4">
            <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Per-stock review · {symbolList.length} symbols on {activeDate}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {symbolList.map((sym) => (
                <Link
                  key={sym}
                  to={`${basePath}/${activeDate}/${sym}`}
                  className="rounded-md border border-border-subtle bg-surface-2 px-2.5 py-1 text-xs font-mono font-bold text-text-primary transition hover:border-accent hover:bg-accent hover:text-white hover:shadow-md hover:shadow-accent/30"
                >
                  {sym}
                </Link>
              ))}
            </div>
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-1 shadow-xl shadow-black/20">
          {isLoading ? (
            <p className="p-6 text-sm text-text-muted">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="p-6 text-sm text-text-muted">No alerts in this session matching your filters.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border-subtle bg-surface-2 text-left text-[11px] uppercase tracking-wider text-text-muted">
                  <tr>
                    <SortableHeader k="time"      label="Time"   align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="symbol"    label="Symbol" align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="direction" label="Dir"    align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="reason"    label="Reason" align="left"   sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="entry"     label="Entry"  align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="stop"      label="Stop"   align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="t1"        label="T1"     align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="t2"        label="T2"     align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="rr"        label="R:R"    align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
                    <SortableHeader k="vol"       label="Vol×"   align="right"  sortKey={sortKey} sortDir={sortDir} onSort={setSort} />
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
                          <Link
                            to={`${basePath}/${activeDate}/${a.symbol}`}
                            className="text-text-primary transition hover:text-accent hover:underline"
                          >
                            {a.symbol}
                          </Link>
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
                          <Link
                            to={`/replay/${a.id}`}
                            className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-3 px-2.5 py-1 font-medium text-text-secondary transition hover:border-accent hover:bg-accent/10 hover:text-accent"
                            title="Open chart replay with entry/stop/T1/T2 overlay"
                          >
                            📈 View
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

        <div className="relative overflow-hidden rounded-2xl border border-border-subtle bg-gradient-to-br from-bullish/15 via-surface-1 to-accent/10 p-6 shadow-lg">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(34,197,94,0.10),transparent_60%)]" />
          <div className="relative flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="font-display text-xl font-bold">Want these signals live in your Telegram?</h2>
              <p className="mt-1 max-w-xl text-sm text-text-muted">
                TradingWithAI fires every signal in real time via Pine indicators on TradingView, then AI-triages each one by sector confluence, volume, and order flow before it hits your phone.
              </p>
            </div>
            <Link
              to="/register"
              className="rounded-lg bg-bullish px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-bullish/30 transition hover:bg-bullish/90 hover:shadow-bullish/50"
            >
              Start free trial →
            </Link>
          </div>
        </div>

        <div className="rounded-lg border border-border-subtle/50 bg-surface-1/40 p-4 text-xs leading-relaxed text-text-muted">
          <p className="mb-2 font-semibold uppercase tracking-wider text-text-secondary">How to read this report</p>
          <ul className="space-y-1">
            <li><span className="font-medium text-text-secondary">R:R</span> — reward-to-risk against T1 (<span className="text-emerald-400">green ≥ 3</span>, <span className="text-amber-400">amber 1.5–3</span>, <span className="text-rose-400">red &lt; 1.5</span>)</li>
            <li><span className="font-medium text-text-secondary">Vol×</span> — fire-bar volume vs average (<span className="text-emerald-400">green ≥ 2.0×</span>, <span className="text-amber-400">amber 1.0–2.0×</span>, <span className="text-rose-400">red &lt; 1.0×</span>)</li>
            <li>Click <span className="font-medium text-accent">📈 View</span> for the chart replay with entry/stop/T1/T2 overlays · Click any column header to sort · Click a symbol to see its per-stock review</li>
          </ul>
        </div>
      </div>
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

function StatTile({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1/60 px-4 py-3 backdrop-blur-sm transition hover:border-border-strong hover:bg-surface-1/80">
      <div className={`font-mono text-2xl font-bold leading-tight ${accent}`}>{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
    </div>
  );
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
