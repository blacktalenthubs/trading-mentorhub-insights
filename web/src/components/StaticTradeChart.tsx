/** StaticTradeChart — quick-look chart view for an alert.
 *
 *  Replaces the cinematic ChartReplay for the public /replay/:id route.
 *  Renders the OHLCV bars around the alert with entry/stop/T1/T2 drawn
 *  as labeled horizontal lines, a marker on the fire bar, and an outcome
 *  label if the alert ran to T1/T2/Stop.
 *
 *  No animation, no controls — just the chart you'd want to glance at
 *  to evaluate whether a setup worked.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  createChart,
  CandlestickSeries,
  ColorType,
  LineStyle,
  createSeriesMarkers,
} from "lightweight-charts";
import type { IChartApi, ISeriesApi, IPriceLine } from "lightweight-charts";
import { X, Share2, ArrowLeft } from "lucide-react";

interface ReplayData {
  alert: {
    id: number;
    symbol: string;
    direction: string;
    alert_type: string;
    price: number;
    entry: number | null;
    stop: number | null;
    target_1: number | null;
    target_2: number | null;
    score: number;
    message: string;
    created_at: string;
    session_date: string;
  };
  bars: Array<{
    timestamp: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  alert_bar_index: number;
  outcome: string;
  outcome_bar_index: number;
  outcome_price: number | null;
  pnl_per_share: number;
  pnl_pct: number;
}

interface Props {
  alertId: number;
}

function prettyReason(alertType: string | null | undefined): string {
  if (!alertType) return "—";
  let t = alertType.replace(/^tv_/, "");
  t = t.replace(/^ma_bounce_long_v3_/, "MA bounce ");
  t = t.replace(/^ma_rejection_short_v3_/, "MA rejection ");
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
  if (p == null) return "—";
  return `$${p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function outcomeLabel(outcome: string): { text: string; color: string } {
  switch (outcome) {
    case "t1_hit":   return { text: "T1 hit",            color: "text-emerald-400" };
    case "t2_hit":   return { text: "T2 hit",            color: "text-emerald-500" };
    case "stop_hit": return { text: "Stopped out",       color: "text-rose-400" };
    case "expired":  return { text: "Expired (no hit)",  color: "text-text-muted" };
    case "open":     return { text: "Still active",      color: "text-amber-400" };
    default:         return { text: outcome || "—",      color: "text-text-muted" };
  }
}

export default function StaticTradeChart({ alertId }: Props) {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  const [data, setData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [shareStatus, setShareStatus] = useState<"idle" | "ok" | "fail">("idle");

  // Fetch replay data
  useEffect(() => {
    fetch(`/api/v1/charts/replay/${alertId}`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d: ReplayData) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => { setError(true); setLoading(false); });
  }, [alertId]);

  // Create + populate chart
  useEffect(() => {
    if (!containerRef.current || !data || data.bars.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0f1c" },
        textColor: "#94a3b8",
        fontSize: 12,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      },
      grid: {
        vertLines: { color: "rgba(148, 163, 184, 0.06)" },
        horzLines: { color: "rgba(148, 163, 184, 0.08)" },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "rgba(148, 163, 184, 0.15)",
        // Bar spacing controls candle width. Default ~6 squishes too tight
        // when there are 100+ bars; ~12 gives readable bodies with wicks
        // visible while still showing meaningful context around the alert.
        barSpacing: 12,
        minBarSpacing: 4,
        rightOffset: 8,
      },
      rightPriceScale: {
        borderColor: "rgba(148, 163, 184, 0.15)",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      crosshair: {
        mode: 1, // Normal — follows mouse, doesn't snap to bars
      },
      autoSize: true,
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444",
    });
    seriesRef.current = series;

    // Convert bars → lightweight-charts format (time in seconds)
    const candleData = data.bars.map((b) => ({
      time: Math.floor(new Date(b.timestamp).getTime() / 1000) as any,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    series.setData(candleData);

    // Draw entry / stop / T1 / T2 as labeled horizontal price lines
    const lines: IPriceLine[] = [];
    if (data.alert.entry) {
      lines.push(series.createPriceLine({
        price: data.alert.entry,
        color: "#3b82f6",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "Entry",
      }));
    }
    if (data.alert.stop) {
      lines.push(series.createPriceLine({
        price: data.alert.stop,
        color: "#ef4444",
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Stop",
      }));
    }
    if (data.alert.target_1) {
      lines.push(series.createPriceLine({
        price: data.alert.target_1,
        color: "#10b981",
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "T1",
      }));
    }
    if (data.alert.target_2) {
      lines.push(series.createPriceLine({
        price: data.alert.target_2,
        color: "#10b981",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "T2",
      }));
    }
    priceLinesRef.current = lines;

    // Mark the alert fire bar + outcome bar
    const markers: any[] = [];
    if (data.alert_bar_index >= 0 && data.alert_bar_index < candleData.length) {
      markers.push({
        time: candleData[data.alert_bar_index].time,
        position: data.alert.direction === "SHORT" ? "aboveBar" : "belowBar",
        color: "#3b82f6",
        shape: data.alert.direction === "SHORT" ? "arrowDown" : "arrowUp",
        text: data.alert.direction === "SHORT" ? "SHORT" : "BUY",
      });
    }
    if (data.outcome_bar_index >= 0 && data.outcome_bar_index < candleData.length && data.outcome) {
      const isWin = data.outcome === "t1_hit" || data.outcome === "t2_hit";
      const isStop = data.outcome === "stop_hit";
      if (isWin || isStop) {
        markers.push({
          time: candleData[data.outcome_bar_index].time,
          position: isWin ? "aboveBar" : "belowBar",
          color: isWin ? "#10b981" : "#ef4444",
          shape: "circle",
          text: outcomeLabel(data.outcome).text,
        });
      }
    }
    if (markers.length > 0) {
      createSeriesMarkers(series, markers);
    }

    // Center the visible window on the alert bar (rather than fitting all
    // bars across the full width, which makes individual candles tiny).
    // Show ~30 bars before the alert + however many follow it, capped so
    // the chart never overflows into uselessly thin candles.
    const totalBars = candleData.length;
    const alertIdx = data.alert_bar_index >= 0 ? data.alert_bar_index : Math.floor(totalBars / 2);
    const PRE_BARS = 30;
    const POST_BARS = 50;
    const from = Math.max(0, alertIdx - PRE_BARS);
    const to = Math.min(totalBars - 1, alertIdx + POST_BARS);
    chart.timeScale().setVisibleLogicalRange({ from, to });

    return () => {
      priceLinesRef.current.forEach((l) => series.removePriceLine(l));
      priceLinesRef.current = [];
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [data]);

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

  const outcome = useMemo(() => data ? outcomeLabel(data.outcome) : null, [data]);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <p className="text-text-muted">Loading chart…</p>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <p className="text-text-muted">Could not load this alert.</p>
      </div>
    );
  }

  const a = data.alert;
  const dirIsLong = a.direction === "BUY" || a.direction === "LONG";

  return (
    <div className="flex min-h-screen flex-col bg-surface-0 text-text-primary">
      {/* Header */}
      <div className="border-b border-border-subtle bg-surface-1/60 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate(-1)}
              className="rounded-lg border border-border-subtle bg-surface-2 p-2 text-text-muted transition hover:border-accent hover:text-accent"
              title="Back"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-display text-xl font-bold">{a.symbol}</h1>
                <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${
                  dirIsLong ? "bg-emerald-500/15 text-emerald-300" :
                  a.direction === "SHORT" ? "bg-rose-500/15 text-rose-300" :
                  "bg-slate-500/15 text-slate-300"
                }`}>
                  {a.direction}
                </span>
                <span className="text-sm text-text-muted">·</span>
                <span className="text-sm font-medium text-text-secondary">{prettyReason(a.alert_type)}</span>
              </div>
              <p className="text-xs text-text-muted">
                Fired {new Date(a.created_at).toLocaleString()} · session {a.session_date}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={copyShareLink}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white transition ${
                shareStatus === "ok"   ? "bg-bullish hover:bg-bullish/90" :
                shareStatus === "fail" ? "bg-rose-500" :
                                          "bg-accent hover:bg-accent-hover"
              }`}
            >
              <Share2 className="h-3.5 w-3.5" />
              {shareStatus === "ok"   ? "Copied" :
               shareStatus === "fail" ? "Failed" :
                                         "Share"}
            </button>
            <button
              onClick={() => navigate("/track-record")}
              className="rounded-lg border border-border-subtle bg-surface-2 p-2 text-text-muted transition hover:border-rose-400 hover:text-rose-400"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Stats strip */}
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-3 px-4 pb-4 sm:grid-cols-5">
          <StatCell label="Entry"   value={formatPrice(a.entry)}    accent="text-blue-400" />
          <StatCell label="Stop"    value={formatPrice(a.stop)}     accent="text-rose-400" />
          <StatCell label="T1"      value={formatPrice(a.target_1)} accent="text-emerald-400" />
          <StatCell label="T2"      value={formatPrice(a.target_2)} accent="text-emerald-500" />
          <StatCell
            label="Outcome"
            value={outcome ? outcome.text : "—"}
            accent={outcome ? outcome.color : "text-text-muted"}
            sub={data.pnl_pct ? `${data.pnl_pct >= 0 ? "+" : ""}${data.pnl_pct.toFixed(2)}%` : undefined}
          />
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 p-4">
        <div className="mx-auto h-full max-w-7xl">
          <div
            ref={containerRef}
            className="w-full rounded-xl border border-border-subtle bg-[#0a0f1c]"
            style={{ height: "min(70vh, 720px)", minHeight: 480 }}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-border-subtle bg-surface-1/40 px-4 py-3">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 text-xs text-text-muted">
          <div>
            <span className="font-semibold text-text-secondary">Legend:</span>
            <span className="ml-2"><span className="text-blue-400">━ Entry</span> · </span>
            <span><span className="text-rose-400">┄ Stop</span> · </span>
            <span><span className="text-emerald-400">┄ T1</span> · </span>
            <span><span className="text-emerald-500">┈ T2</span></span>
          </div>
          <Link
            to="/register"
            className="rounded-md bg-bullish px-3 py-1.5 text-xs font-semibold text-white hover:bg-bullish/90"
          >
            Get live alerts →
          </Link>
        </div>
      </div>
    </div>
  );
}

function StatCell({ label, value, accent, sub }: { label: string; value: string; accent: string; sub?: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-2/60 px-3 py-2">
      <div className={`font-mono text-base font-bold leading-tight ${accent}`}>{value}</div>
      <div className="mt-0.5 flex items-baseline gap-1 text-[11px] uppercase tracking-wider text-text-muted">
        <span>{label}</span>
        {sub && <span className={accent}>{sub}</span>}
      </div>
    </div>
  );
}
