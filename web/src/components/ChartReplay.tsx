/** Chart Replay — animated candle-by-candle playback of past alerts.
 *
 *  Usage:
 *    <ChartReplay alertId={1234} onClose={() => setShowReplay(false)} />
 */

import { useEffect, useRef, useState } from "react";
import { createChart, CandlestickSeries, ColorType } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { Play, Pause, SkipBack, SkipForward, X } from "lucide-react";

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
      height: 300,
      crosshair: { mode: 1 },
      rightPriceScale: {
        autoScale: true,
        scaleMargins: { top: 0.1, bottom: 0.1 },
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
      series.createPriceLine({ price: a.entry, color: "#3b82f6", lineWidth: 1, lineStyle: 2, title: `Entry $${a.entry}` });
    }
    if (a.stop) {
      series.createPriceLine({ price: a.stop, color: "#ef4444", lineWidth: 1, lineStyle: 2, title: `Stop $${a.stop}` });
    }
    if (a.target_1) {
      series.createPriceLine({ price: a.target_1, color: "#22c55e", lineWidth: 1, lineStyle: 2, title: `T1 $${a.target_1}` });
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [data]);

  // Update visible bars
  useEffect(() => {
    if (!seriesRef.current || !data || data.bars.length === 0) return;

    const visible = data.bars.slice(0, visibleCount).map((b) => {
      // Convert timestamp to lightweight-charts format
      const d = new Date(b.timestamp);
      return {
        time: (d.getTime() / 1000) as any,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      };
    });

    // Dedup timestamps
    const seen = new Set<number>();
    const deduped = visible.filter((v) => {
      if (seen.has(v.time)) return false;
      seen.add(v.time);
      return true;
    });

    seriesRef.current.setData(deduped);

    // Check if outcome reached
    if (visibleCount >= data.outcome_bar_index && data.outcome !== "open") {
      setShowOutcome(true);
    }
  }, [visibleCount, data]);

  // Animation loop
  useEffect(() => {
    if (!playing || !data) return;
    const timer = setInterval(() => {
      setVisibleCount((prev) => {
        if (prev >= data.bars.length) {
          setPlaying(false);
          return data.bars.length;
        }
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
  const outcomeLabel = data.outcome === "target_1_hit" ? "TARGET 1 HIT"
    : data.outcome === "target_2_hit" ? "TARGET 2 HIT"
    : data.outcome === "stop_loss_hit" ? "STOPPED OUT"
    : data.outcome === "auto_stop_out" ? "AUTO STOPPED"
    : "OPEN";

  return (
    <div className="fixed inset-0 z-50 bg-surface-0/95 flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-surface-1 border border-border-subtle rounded-xl overflow-hidden shadow-elevated">
        {/* Header */}
        <div className="px-5 py-3 border-b border-border-subtle flex items-center justify-between">
          <div>
            <h3 className="font-bold text-text-primary flex items-center gap-2">
              {a.symbol}
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                a.direction === "BUY" ? "bg-bullish/10 text-bullish-text" : "bg-bearish/10 text-bearish-text"
              }`}>
                {a.direction === "BUY" ? "LONG" : "SHORT"}
              </span>
              <span className="text-xs text-text-muted font-normal">{a.alert_type}</span>
            </h3>
            <p className="text-[10px] text-text-faint">Score {a.score} · {a.message?.slice(0, 60)}</p>
          </div>
          <button onClick={onClose} className="text-text-faint hover:text-text-muted">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Chart */}
        <div ref={containerRef} className="w-full" />

        {/* Controls */}
        <div className="px-5 py-3 border-t border-border-subtle flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setVisibleCount(Math.max(1, data.alert_bar_index)); setShowOutcome(false); setPlaying(false); }}
              className="p-1.5 rounded hover:bg-surface-3 text-text-muted"
              title="Reset to alert moment"
            >
              <SkipBack className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPlaying(!playing)}
              className="p-2 rounded-full bg-accent hover:bg-accent-hover text-white"
            >
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button
              onClick={() => { setVisibleCount(data.bars.length); setPlaying(false); setShowOutcome(data.outcome !== "open"); }}
              className="p-1.5 rounded hover:bg-surface-3 text-text-muted"
              title="Jump to outcome"
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
                className={`px-2 py-0.5 rounded text-[10px] font-bold transition-colors ${
                  speed === s ? "bg-accent/20 text-accent" : "text-text-faint hover:text-text-muted"
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Progress */}
          <span className="text-[10px] text-text-faint font-mono">
            {visibleCount}/{data.bars.length} bars
          </span>
        </div>

        {/* Outcome banner */}
        {showOutcome && (
          <div className={`px-5 py-3 text-center font-bold text-sm ${
            isWin ? "bg-bullish/10 text-bullish-text" : "bg-bearish/10 text-bearish-text"
          }`}>
            {isWin ? "🟢" : "🔴"} {outcomeLabel}
            {data.outcome_price && ` — $${data.outcome_price.toFixed(2)}`}
            {` (${data.pnl_pct >= 0 ? "+" : ""}${data.pnl_pct}%)`}
          </div>
        )}
      </div>
    </div>
  );
}
