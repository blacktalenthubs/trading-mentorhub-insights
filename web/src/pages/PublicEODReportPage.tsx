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
import Card from "../components/ui/Card";
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
    return alerts
      // Drop NOTICE alerts entirely — public report shows actionable BUY/SHORT only.
      .filter((a) => a.direction !== "NOTICE")
      .filter((a) => dirFilter === "All" || a.direction === dirFilter)
      .filter((a) =>
        !symFilter ? true : a.symbol.toUpperCase().includes(symFilter.toUpperCase()),
      );
  }, [alerts, dirFilter, symFilter]);

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

  // Unique symbols in the day's stream — used as the per-stock review jump list
  const symbolList = useMemo(() => {
    const set = new Set<string>();
    (alerts || []).forEach((a) => set.add(a.symbol));
    return Array.from(set).sort();
  }, [alerts]);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      {/* Public hero / CTA banner */}
      <div className="border-b border-border-subtle bg-gradient-to-r from-accent/10 via-surface-1 to-bullish/10 px-6 py-4">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl font-bold">
              Mentorhub — EOD Alert Report
              {focusSymbol && (
                <span className="ml-2 rounded bg-accent/20 px-2 py-1 align-middle text-base text-accent">
                  {focusSymbol}
                </span>
              )}
            </h1>
            <p className="text-sm text-text-muted">
              {focusSymbol
                ? `Every alert that fired for ${focusSymbol} on this session — entry, stop, targets, and rule.`
                : "Every alert our Pine indicators fired for this session — public view. Click any row for the chart replay."}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={copyShareLink}
              className={`rounded px-3 py-1.5 text-xs font-medium text-white transition ${
                shareStatus === "ok" ? "bg-bullish hover:bg-bullish/90" :
                shareStatus === "fail" ? "bg-bearish-text" :
                                          "bg-accent hover:bg-accent-hover"
              }`}
              title="Copy this page's URL to share"
            >
              {shareStatus === "ok" ? "✓ Link copied" :
               shareStatus === "fail" ? "✗ Copy failed" :
                                         "🔗 Copy share link"}
            </button>
            <Link
              to="/register"
              className="rounded bg-bullish px-3 py-1.5 text-xs font-medium text-white hover:bg-bullish/90"
            >
              Get live alerts →
            </Link>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-7xl space-y-4 p-6">
        {/* Date + filters */}
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={activeDate}
            onChange={(e) => selectDate(e.target.value)}
            className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary"
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
              placeholder="Filter symbol..."
              className="rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
            />
          )}

          <div className="flex gap-1">
            {DIRECTION_FILTERS.map((f) => (
              <button
                key={f}
                onClick={() => setDirFilter(f)}
                className={`rounded px-3 py-1.5 text-xs font-medium transition ${
                  dirFilter === f ? "bg-accent text-white" : "bg-surface-3 text-text-muted hover:text-text-primary"
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
              className="ml-auto rounded border border-border-subtle bg-surface-3 px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
            >
              ← Back to all symbols
            </Link>
          )}
        </div>

        {/* Per-stock jump list (only on the full session view) */}
        {!focusSymbol && symbolList.length > 0 && (
          <Card>
            <div className="p-3">
              <p className="mb-2 text-xs uppercase text-text-muted">
                Per-stock review — click a symbol to see only its alerts for {activeDate}:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {symbolList.map((sym) => (
                  <Link
                    key={sym}
                    to={`${basePath}/${activeDate}/${sym}`}
                    className="rounded bg-surface-3 px-2 py-1 text-xs font-mono font-semibold text-text-primary transition hover:bg-accent hover:text-white"
                  >
                    {sym}
                  </Link>
                ))}
              </div>
            </div>
          </Card>
        )}

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
                    <th className="px-3 py-2 text-center font-medium">Chart</th>
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
                          <Link
                            to={`${basePath}/${activeDate}/${a.symbol}`}
                            className="text-text-primary hover:text-accent hover:underline"
                          >
                            {a.symbol}
                          </Link>
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
                          <Link
                            to={`/replay/${a.id}`}
                            className="rounded border border-border-subtle bg-surface-3 px-2 py-1 hover:border-accent hover:text-accent"
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
        </Card>

        <div className="rounded-lg border border-border-subtle bg-surface-1 p-4">
          <h2 className="mb-2 font-display text-lg font-semibold">Want these alerts live in your Telegram?</h2>
          <p className="mb-3 text-sm text-text-muted">
            Mentorhub fires these signals via Pine indicators on TradingView and delivers them to your phone the moment they cross — with AI triage that ranks each by sector confluence, volume, and order flow.
          </p>
          <Link
            to="/register"
            className="inline-block rounded bg-bullish px-4 py-2 text-sm font-medium text-white hover:bg-bullish/90"
          >
            Start free trial →
          </Link>
        </div>

        <p className="text-xs text-text-muted">
          <span className="font-medium">R:R</span> = reward-to-risk against T1 (green ≥ 3, amber 1.5–3, red &lt; 1.5).{" "}
          <span className="font-medium">Vol×</span> = fire-bar volume vs average (green ≥ 2.0×, amber 1.0–2.0×, red &lt; 1.0×).{" "}
          Click <span className="font-medium">📈 View</span> for the chart replay with entry/stop/T1/T2 overlays.
        </p>
      </div>
    </div>
  );
}
