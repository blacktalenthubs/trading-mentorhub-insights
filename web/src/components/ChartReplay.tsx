/** Chart Replay — animated candle-by-candle playback of past alerts.
 *
 *  Shows the alert context, entry/stop/target lines, and animates price
 *  action forward with a running P&L counter. Clear connection between
 *  the alert that fired and the outcome.
 */

import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, ColorType } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { Play, Pause, SkipBack, SkipForward, X, Target, ShieldAlert } from "lucide-react";

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
  onClose: () => void;
}

function fmt(v: number | null | undefined): string {
  return v != null ? v.toFixed(2) : "—";
}

export default function ChartReplay({ alertId, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [data, setData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [visibleCount, setVisibleCount] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [showOutcome, setShowOutcome] = useState(false);

  // Live P&L tracking during animation
  const currentPrice = data && visibleCount > 0 && visibleCount <= data.bars.length
    ? data.bars[visibleCount - 1]?.close ?? 0 : 0;
  const entry = data?.alert.entry ?? 0;
  const livePnl = entry && currentPrice
    ? (data?.alert.direction === "SHORT" ? entry - currentPrice : currentPrice - entry)
    : 0;
  const livePnlPct = entry ? (livePnl / entry) * 100 : 0;

  // Progress percentage
  const progress = data ? (visibleCount / data.bars.length) * 100 : 0;

  // Fetch replay data
  useEffect(() => {
    fetch(`/api/v1/charts/replay/${alertId}`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => {
        setData(d);
        setVisibleCount(Math.max(1, d.alert_bar_index));
        setLoading(false);
      })
      .catch(() => { setError(true); setLoading(false); });
  }, [alertId]);

  // Create chart
  useEffect(() => {
    if (!containerRef.current || !data || data.bars.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0f1a" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.03)" },
        horzLines: { color: "rgba(255,255,255,0.03)" },
      },
      width: containerRef.current.clientWidth,
      height: 320,
      crosshair: { mode: 1 },
      rightPriceScale: {
        autoScale: true,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: { rightOffset: 3 },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef4444",
      wickUpColor: "#22c55e",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    // Draw price lines
    const a = data.alert;
    if (a.entry) {
      series.createPriceLine({ price: a.entry, color: "#3b82f6", lineWidth: 2, lineStyle: 0, title: `Entry $${fmt(a.entry)}` });
    }
    if (a.stop) {
      series.createPriceLine({ price: a.stop, color: "#ef4444", lineWidth: 1, lineStyle: 2, title: `Stop $${fmt(a.stop)}` });
    }
    if (a.target_1) {
      series.createPriceLine({ price: a.target_1, color: "#22c55e", lineWidth: 1, lineStyle: 2, title: `T1 $${fmt(a.target_1)}` });
    }

    const handleResize = () => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    };
    window.addEventListener("resize", handleResize);
    return () => { window.removeEventListener("resize", handleResize); chart.remove(); };
  }, [data]);

  // Update visible bars
  useEffect(() => {
    if (!seriesRef.current || !data || data.bars.length === 0) return;

    const visible = data.bars.slice(0, visibleCount).map((b) => {
      const d = new Date(b.timestamp);
      return { time: (d.getTime() / 1000) as any, open: b.open, high: b.high, low: b.low, close: b.close };
    });

    const seen = new Set<number>();
    const deduped = visible.filter((v) => { if (seen.has(v.time)) return false; seen.add(v.time); return true; });
    seriesRef.current.setData(deduped);

    if (visibleCount >= data.outcome_bar_index && data.outcome !== "open") {
      setShowOutcome(true);
      setPlaying(false);
    }
  }, [visibleCount, data]);

  // Animation loop
  useEffect(() => {
    if (!playing || !data) return;
    const timer = setInterval(() => {
      setVisibleCount((prev) => {
        if (prev >= data.bars.length) { setPlaying(false); return data.bars.length; }
        return prev + 1;
      });
    }, 400 / speed);
    return () => clearInterval(timer);
  }, [playing, speed, data]);

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 bg-surface-0/90 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error || !data || data.bars.length === 0) {
    return (
      <div className="fixed inset-0 z-50 bg-surface-0/90 flex flex-col items-center justify-center gap-3">
        <p className="text-text-muted">Replay not available for this alert</p>
        <button onClick={onClose} className="text-sm text-accent">Close</button>
      </div>
    );
  }

  const a = data.alert;
  const isWin = data.outcome.includes("target");
  const isBuy = a.direction === "BUY";
  const outcomeLabel = data.outcome === "target_1_hit" ? "TARGET 1 HIT"
    : data.outcome === "target_2_hit" ? "TARGET 2 HIT"
    : data.outcome === "stop_loss_hit" ? "STOPPED OUT"
    : data.outcome === "auto_stop_out" ? "AUTO STOPPED"
    : "TRADE OPEN";

  return (
    <div className="fixed inset-0 z-50 bg-surface-0/95 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl bg-surface-1 border border-border-subtle rounded-xl overflow-hidden shadow-elevated">

        {/* Header — Alert Context */}
        <div className="px-5 py-4 border-b border-border-subtle bg-surface-2/20">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg font-bold text-text-primary">{a.symbol}</span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  isBuy ? "bg-bullish/10 text-bullish-text border border-bullish/20" : "bg-bearish/10 text-bearish-text border border-bearish/20"
                }`}>
                  {isBuy ? "LONG" : "SHORT"}
                </span>
                <span className="text-xs text-text-muted bg-surface-3 px-2 py-0.5 rounded">{a.alert_type}</span>
                <span className="text-xs text-text-faint">Score {a.score}</span>
              </div>
              {/* Trade plan strip */}
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="text-accent">Entry ${fmt(a.entry)}</span>
                <span className="text-bearish-text">Stop ${fmt(a.stop)}</span>
                <span className="text-bullish-text">T1 ${fmt(a.target_1)}</span>
                {a.target_2 && <span className="text-bullish-text/70">T2 ${fmt(a.target_2)}</span>}
              </div>
            </div>

            {/* Live P&L */}
            <div className="text-right ml-4">
              <div className={`font-mono text-xl font-bold ${livePnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                {livePnl >= 0 ? "+" : ""}{livePnl.toFixed(2)}
              </div>
              <div className={`text-xs font-mono ${livePnl >= 0 ? "text-bullish-text/70" : "text-bearish-text/70"}`}>
                {livePnlPct >= 0 ? "+" : ""}{livePnlPct.toFixed(2)}%
              </div>
            </div>

            <button onClick={onClose} className="text-text-faint hover:text-text-muted ml-3">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Alert message */}
          {a.message && (
            <p className="mt-2 text-xs text-text-secondary leading-relaxed">{a.message.slice(0, 120)}</p>
          )}
        </div>

        {/* Chart */}
        <div ref={containerRef} className="w-full" />

        {/* Progress bar */}
        <div className="h-1 bg-surface-3">
          <div
            className={`h-full transition-all duration-200 ${showOutcome ? (isWin ? "bg-bullish" : "bg-bearish") : "bg-accent"}`}
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Controls */}
        <div className="px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => { setVisibleCount(Math.max(1, data.alert_bar_index)); setShowOutcome(false); setPlaying(false); }}
              className="p-1.5 rounded hover:bg-surface-3 text-text-muted transition-colors"
              title="Reset to alert"
            >
              <SkipBack className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPlaying(!playing)}
              className="p-2.5 rounded-full bg-accent hover:bg-accent-hover text-white transition-colors"
            >
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button
              onClick={() => { setVisibleCount(data.bars.length); setPlaying(false); setShowOutcome(data.outcome !== "open"); }}
              className="p-1.5 rounded hover:bg-surface-3 text-text-muted transition-colors"
              title="Skip to outcome"
            >
              <SkipForward className="h-4 w-4" />
            </button>
          </div>

          {/* Speed */}
          <div className="flex items-center gap-1">
            {[1, 2, 5].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-2.5 py-1 rounded text-xs font-bold transition-colors ${
                  speed === s ? "bg-accent/20 text-accent" : "text-text-faint hover:text-text-muted"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Bar counter */}
          <span className="text-xs text-text-faint font-mono">
            Bar {visibleCount}/{data.bars.length}
          </span>
        </div>

        {/* Outcome banner */}
        {showOutcome && (
          <div className={`px-5 py-4 flex items-center justify-between ${
            isWin ? "bg-bullish/10 border-t border-bullish/20" : "bg-bearish/10 border-t border-bearish/20"
          }`}>
            <div className="flex items-center gap-3">
              {isWin ? <Target className="h-5 w-5 text-bullish-text" /> : <ShieldAlert className="h-5 w-5 text-bearish-text" />}
              <div>
                <span className={`font-bold text-sm ${isWin ? "text-bullish-text" : "text-bearish-text"}`}>
                  {outcomeLabel}
                </span>
                {data.outcome_price && (
                  <span className="text-xs text-text-muted ml-2">
                    at ${data.outcome_price.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            <div className="text-right">
              <span className={`font-mono text-lg font-bold ${isWin ? "text-bullish-text" : "text-bearish-text"}`}>
                {data.pnl_pct >= 0 ? "+" : ""}{data.pnl_pct}%
              </span>
              <span className="text-xs text-text-faint ml-2">
                (${data.pnl_per_share >= 0 ? "+" : ""}{data.pnl_per_share}/share)
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
