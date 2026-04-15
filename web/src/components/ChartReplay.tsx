/** Chart Replay — cinematic candle-by-candle trade replay for demo & marketing.
 *
 *  Phases: SETUP → APPROACH → ENTRY → MOVE → TARGET/STOP → RESULT
 *  Full-screen first, visual highlights at key moments, result card overlay.
 */

import { useEffect, useRef, useState, useMemo } from "react";
import { createChart, CandlestickSeries, ColorType, createSeriesMarkers } from "lightweight-charts";
import type { IChartApi, ISeriesApi, ISeriesMarkersPluginApi } from "lightweight-charts";
import { Play, Pause, SkipBack, SkipForward, X, Maximize2, Minimize2 } from "lucide-react";
import { useAuthStore } from "../stores/auth";

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

const SETUP_LABELS: Record<string, string> = {
  session_low_double_bottom: "Session Low Double Bottom",
  prior_day_low_bounce: "Prior Day Low Bounce",
  prior_day_low_reclaim: "Prior Day Low Reclaim",
  vwap_reclaim: "VWAP Reclaim",
  vwap_bounce: "VWAP Bounce",
  ma_bounce_20: "20 MA Bounce",
  ma_bounce_50: "50 MA Bounce",
  ma_bounce_100: "100 MA Bounce",
  ma_bounce_200: "200 MA Bounce",
  ema_bounce_50: "50 EMA Bounce",
  ema_bounce_100: "100 EMA Bounce",
  ema_bounce_200: "200 EMA Bounce",
  prior_day_high_breakout: "PDH Breakout",
  pdh_retest_hold: "PDH Retest & Hold",
  session_high_double_top: "Session High Double Top",
  pdh_failed_breakout: "PDH Failed Breakout",
  ema_rejection_short: "EMA Rejection",
  weekly_high_breakout: "Weekly High Breakout",
  consol_breakout_long: "Consolidation Breakout",
  fib_retracement_bounce: "Fibonacci Bounce",
  ai_scan_long: "AI Scan — Long",
  ai_scan_short: "AI Scan — Short",
  morning_low_retest: "Morning Low Retest",
  multi_day_double_bottom: "Multi-Day Double Bottom",
  gap_and_go: "Gap & Go",
  bb_squeeze_breakout: "Bollinger Squeeze Breakout",
  session_low_reversal: "Session Low Reversal",
};

function fmt(v: number | null | undefined): string {
  return v != null ? v.toFixed(2) : "—";
}

type Phase = "setup" | "approach" | "entry" | "move" | "target" | "result";

export default function ChartReplay({ alertId, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<any> | null>(null);

  const [data, setData] = useState<ReplayData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [visibleCount, setVisibleCount] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1); // Start at 1x — slow and clear
  const [fullscreen, setFullscreen] = useState(true); // Start fullscreen
  const [linkCopied, setLinkCopied] = useState(false);

  // Derived state
  const currentPrice = data && visibleCount > 0 && visibleCount <= data.bars.length
    ? data.bars[visibleCount - 1]?.close ?? 0 : 0;
  const entry = data?.alert.entry ?? 0;
  const isBuy = data?.alert.direction === "BUY";
  const livePnl = entry && currentPrice
    ? (isBuy ? currentPrice - entry : entry - currentPrice) : 0;
  const livePnlPct = entry ? (livePnl / entry) * 100 : 0;
  const progress = data ? (visibleCount / data.bars.length) * 100 : 0;
  const isWin = data?.outcome?.includes("target") ?? false;

  const setupLabel = data ? (SETUP_LABELS[data.alert.alert_type] || data.alert.alert_type.replace(/_/g, " ")) : "";

  // Phase calculation
  const phase: Phase = useMemo(() => {
    if (!data) return "setup";
    const alertIdx = data.alert_bar_index;
    const outcomeIdx = data.outcome_bar_index || data.bars.length;

    if (visibleCount <= Math.max(1, alertIdx - 4)) return "setup";
    if (visibleCount <= alertIdx) return "approach";
    if (visibleCount <= alertIdx + 2) return "entry";
    if (visibleCount < outcomeIdx) return "move";
    if (visibleCount <= outcomeIdx + 2) return "target";
    return "result";
  }, [data, visibleCount]);

  const outcomeLabel = data?.outcome === "target_1_hit" ? "TARGET 1 HIT"
    : data?.outcome === "target_2_hit" ? "TARGET 2 HIT"
    : data?.outcome === "stop_loss_hit" ? "STOPPED OUT"
    : data?.outcome === "auto_stop_out" ? "AUTO STOPPED"
    : "TRADE OPEN";

  // Duration
  const duration = useMemo(() => {
    if (!data || !data.bars.length) return "";
    const alertTime = new Date(data.bars[data.alert_bar_index]?.timestamp || "");
    const outcomeIdx = Math.min(data.outcome_bar_index, data.bars.length - 1);
    const outcomeTime = new Date(data.bars[outcomeIdx]?.timestamp || "");
    const diffMin = Math.round((outcomeTime.getTime() - alertTime.getTime()) / 60000);
    if (diffMin < 60) return `${diffMin} min`;
    return `${Math.floor(diffMin / 60)}h ${diffMin % 60}m`;
  }, [data]);

  // Fetch replay data
  useEffect(() => {
    const token = useAuthStore.getState().accessToken;
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;

    fetch(`/api/v1/charts/replay/${alertId}`, { headers })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => {
        setData(d);
        // Start with ~20 bars of pre-entry context so chart has visual depth
        setVisibleCount(Math.max(1, d.alert_bar_index - 20));
        setLoading(false);
        setTimeout(() => setPlaying(true), 2000);
      })
      .catch(() => { setError(true); setLoading(false); });
  }, [alertId]);

  // Create chart
  useEffect(() => {
    if (!containerRef.current || !data || data.bars.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#080d19" },
        textColor: "#64748b",
        fontSize: 13,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.02)" },
        horzLines: { color: "rgba(255,255,255,0.02)" },
      },
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight || 500,
      crosshair: { mode: 0 }, // No crosshair during replay
      rightPriceScale: {
        autoScale: true,
        // Bigger margins so entry / stop / T1 / T2 lines all sit inside the
        // visible price range (not cut off by candle-only auto-fit)
        scaleMargins: { top: 0.22, bottom: 0.22 },
        borderVisible: false,
      },
      timeScale: {
        rightOffset: 2,
        barSpacing: 9,   // moderate — readable but not huge blocks
        minBarSpacing: 4,
        borderVisible: false,
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: "#ef444480",
      wickUpColor: "#22c55e80",
    });

    // Force price scale to include entry/stop/T1/T2 so level lines always render
    try {
      const a = data.alert;
      const levels = [a.entry, a.stop, a.target_1, a.target_2].filter((x): x is number => !!x && x > 0);
      if (levels.length > 0) {
        series.applyOptions({
          autoscaleInfoProvider: (original: any) => {
            const r = original();
            if (!r || !r.priceRange) return r;
            const curMin = r.priceRange.minValue;
            const curMax = r.priceRange.maxValue;
            const lvlMin = Math.min(...levels);
            const lvlMax = Math.max(...levels);
            return {
              ...r,
              priceRange: {
                minValue: Math.min(curMin, lvlMin),
                maxValue: Math.max(curMax, lvlMax),
              },
            };
          },
        } as any);
      }
    } catch {
      // autoscaleInfoProvider unavailable — ignore
    }

    chartRef.current = chart;
    seriesRef.current = series;
    // v5 markers API — attach plugin once, reuse for updates
    try {
      markersRef.current = createSeriesMarkers(series, []);
    } catch {
      markersRef.current = null;
    }

    // Draw key level lines
    const a = data.alert;
    if (a.entry) {
      series.createPriceLine({
        price: a.entry, color: "#3b82f6", lineWidth: 3, lineStyle: 0,
        title: `▶ ENTRY $${fmt(a.entry)}`,
        axisLabelVisible: true,
      });
    }
    if (a.stop) {
      series.createPriceLine({
        price: a.stop, color: "#ef4444", lineWidth: 2, lineStyle: 2,
        title: `✖ STOP $${fmt(a.stop)}`,
        axisLabelVisible: true,
      });
    }
    if (a.target_1) {
      series.createPriceLine({
        price: a.target_1, color: "#22c55e", lineWidth: 3, lineStyle: 0,
        title: `✔ T1 $${fmt(a.target_1)}`,
        axisLabelVisible: true,
      });
    }
    if (a.target_2) {
      series.createPriceLine({
        price: a.target_2, color: "#22c55e80", lineWidth: 2, lineStyle: 2,
        title: `T2 $${fmt(a.target_2)}`,
        axisLabelVisible: true,
      });
    }

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 500,
        });
      }
    };
    window.addEventListener("resize", handleResize);
    return () => { window.removeEventListener("resize", handleResize); chart.remove(); };
  }, [data]);

  // Resize on fullscreen toggle
  useEffect(() => {
    if (chartRef.current && containerRef.current) {
      setTimeout(() => {
        chartRef.current?.applyOptions({
          width: containerRef.current!.clientWidth,
          height: containerRef.current!.clientHeight || 500,
        });
      }, 50);
    }
  }, [fullscreen]);

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

    // Auto-fit the visible bars to chart width so candles aren't clustered right
    try {
      chartRef.current?.timeScale().fitContent();
    } catch {}

    // Entry / exit markers on candles (v5 API via plugin)
    if (markersRef.current) {
      const markers: any[] = [];
      const alertIdx = data.alert_bar_index;
      const outcomeIdx = data.outcome_bar_index;
      if (alertIdx < visibleCount) {
        const bar = data.bars[alertIdx];
        if (bar) {
          markers.push({
            time: (new Date(bar.timestamp).getTime() / 1000) as any,
            position: isBuy ? "belowBar" : "aboveBar",
            color: "#3b82f6",
            shape: isBuy ? "arrowUp" : "arrowDown",
            text: `${isBuy ? "LONG" : "SHORT"} $${fmt(data.alert.entry)}`,
          });
        }
      }
      if (outcomeIdx != null && outcomeIdx > 0 && outcomeIdx < visibleCount) {
        const bar = data.bars[outcomeIdx];
        if (bar) {
          const isWinOutcome = data.outcome?.includes("target");
          markers.push({
            time: (new Date(bar.timestamp).getTime() / 1000) as any,
            position: isWinOutcome ? "aboveBar" : "belowBar",
            color: isWinOutcome ? "#22c55e" : "#ef4444",
            shape: isWinOutcome ? "arrowDown" : "arrowUp",
            text: isWinOutcome ? `✓ EXIT $${fmt(data.outcome_price)}` : `✖ STOP $${fmt(data.outcome_price)}`,
          });
        }
      }
      try {
        markersRef.current.setMarkers(markers);
      } catch {}
    }
  }, [visibleCount, data, isBuy]);

  // Animation loop
  useEffect(() => {
    if (!playing || !data) return;
    // Target total replay ~35s so viewer can follow candle-by-candle.
    // Move phase dominates (10-20 bars) so it paces the story.
    const interval = phase === "entry" || phase === "target" ? 3000  // 3s emphasis
      : phase === "approach" ? 2000
      : phase === "setup" ? 3500  // 3.5s per setup bar — reads AI reason clearly
      : phase === "result" ? 4000
      : 1400; // move phase — 1.4s per bar, candles build gradually
    const timer = setInterval(() => {
      setVisibleCount((prev) => {
        if (prev >= data.bars.length) { setPlaying(false); return data.bars.length; }
        return prev + 1;
      });
    }, interval / speed);
    return () => clearInterval(timer);
  }, [playing, speed, data, phase]);

  // Auto-pause at result
  useEffect(() => {
    if (phase === "result" && playing) {
      setTimeout(() => setPlaying(false), 1000);
    }
  }, [phase]);

  function shareReplay() {
    const url = `${window.location.origin}/replay/${alertId}`;
    navigator.clipboard.writeText(url);
    setLinkCopied(true);
    setTimeout(() => setLinkCopied(false), 2000);
  }

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 bg-[#080d19] flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-text-muted text-sm">Loading replay...</p>
        </div>
      </div>
    );
  }

  if (error || !data || data.bars.length === 0) {
    return (
      <div className="fixed inset-0 z-50 bg-[#080d19] flex flex-col items-center justify-center gap-3">
        <p className="text-text-muted">Replay not available for this alert</p>
        <button onClick={onClose} className="text-sm text-accent">Close</button>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 bg-[#080d19] flex flex-col">

      {/* ── Phase Overlays ── */}
      <div className="absolute inset-0 z-10 pointer-events-none">

        {/* SETUP phase: show trade name prominently + AI reason */}
        {phase === "setup" && (
          <div className="absolute top-12 left-8 right-8 animate-in fade-in slide-in-from-left duration-700 max-w-2xl">
            <div className="text-3xl font-bold text-white tracking-tight">
              {setupLabel.toUpperCase()}
            </div>
            <div className="text-lg text-accent mt-1 font-mono">
              {data.alert.symbol} — ${fmt(data.alert.price)}
            </div>
            <div className="flex gap-4 mt-2 text-sm font-mono">
              <span className="text-blue-400">Entry ${fmt(data.alert.entry)}</span>
              <span className="text-red-400">Stop ${fmt(data.alert.stop)}</span>
              <span className="text-emerald-400">T1 ${fmt(data.alert.target_1)}</span>
            </div>
            {data.alert.message && (
              <div className="mt-3 text-[13px] text-text-secondary bg-[#0f1629]/80 border border-white/5 rounded-lg p-3 backdrop-blur-sm">
                <span className="text-[10px] uppercase tracking-wider text-text-faint">AI Reason</span>
                <div className="mt-1 leading-relaxed">{data.alert.message}</div>
              </div>
            )}
          </div>
        )}

        {/* Persistent outcome tag (top right) — always shows while replay is in MOVE/TARGET */}
        {(phase === "move" || phase === "target") && data.outcome && (
          <div className="absolute top-6 left-8 text-[10px] uppercase tracking-widest text-text-faint">
            Outcome: <span className={isWin ? "text-emerald-400" : "text-red-400"}>{outcomeLabel}</span>
            {data.pnl_pct !== 0 && (
              <span className="ml-2 font-mono">
                ({data.pnl_pct >= 0 ? "+" : ""}{data.pnl_pct}%)
              </span>
            )}
          </div>
        )}

        {/* APPROACH phase: tension text */}
        {phase === "approach" && (
          <div className="absolute top-8 left-8">
            <div className="text-sm text-text-muted uppercase tracking-widest animate-pulse">
              Approaching {isBuy ? "support" : "resistance"}...
            </div>
          </div>
        )}

        {/* ENTRY phase: compact top-center pill (does not block chart) */}
        {phase === "entry" && (
          <div className="absolute top-8 left-1/2 -translate-x-1/2 animate-in fade-in zoom-in duration-300 bg-accent/15 border border-accent/40 rounded-full px-6 py-2 backdrop-blur-sm">
            <div className="text-sm font-bold text-accent text-center">
              {isBuy ? "ENTRY" : "SHORT ENTRY"} · ${fmt(data.alert.entry)}
            </div>
          </div>
        )}

        {/* MOVE phase: live P&L counter */}
        {phase === "move" && (
          <div className="absolute top-6 right-8">
            <div className={`text-3xl font-mono font-bold tabular-nums ${livePnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {livePnl >= 0 ? "+" : ""}{livePnl.toFixed(2)}
            </div>
            <div className={`text-sm font-mono text-right ${livePnl >= 0 ? "text-emerald-400/70" : "text-red-400/70"}`}>
              {livePnlPct >= 0 ? "+" : ""}{livePnlPct.toFixed(2)}%
            </div>
          </div>
        )}

        {/* TARGET HIT phase: compact top-center pill (does not block chart) */}
        {phase === "target" && (
          <div className={`absolute top-8 left-1/2 -translate-x-1/2 animate-in fade-in zoom-in duration-500 rounded-full px-6 py-2 backdrop-blur-sm border ${
            isWin ? "bg-emerald-500/15 border-emerald-500/40" : "bg-red-500/15 border-red-500/40"
          }`}>
            <div className={`text-sm font-bold text-center ${isWin ? "text-emerald-400" : "text-red-400"}`}>
              {outcomeLabel} · {data.pnl_pct >= 0 ? "+" : ""}{data.pnl_pct}%
            </div>
          </div>
        )}

        {/* RESULT phase: result card overlay */}
        {phase === "result" && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm pointer-events-auto">
            <div className="bg-[#0f1629] border border-white/10 rounded-2xl p-8 max-w-md shadow-2xl">
              <div className="flex items-center gap-3 mb-6">
                <span className="text-3xl">{isWin ? "✅" : "🛑"}</span>
                <span className={`text-2xl font-bold ${isWin ? "text-emerald-400" : "text-red-400"}`}>
                  {outcomeLabel}
                </span>
              </div>
              <div className="space-y-3 text-base">
                <div className="flex justify-between">
                  <span className="text-gray-400">Symbol</span>
                  <span className="text-white font-bold text-lg">{data.alert.symbol}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Setup</span>
                  <span className="text-accent font-medium">{setupLabel}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Entry</span>
                  <span className="text-white font-mono">${fmt(data.alert.entry)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Exit</span>
                  <span className="text-white font-mono">${fmt(data.outcome_price)}</span>
                </div>
                <div className="flex justify-between border-t border-white/10 pt-3">
                  <span className="text-gray-400">P&L</span>
                  <span className={`font-bold font-mono text-lg ${isWin ? "text-emerald-400" : "text-red-400"}`}>
                    {data.pnl_pct >= 0 ? "+" : ""}{data.pnl_pct}%
                    <span className="text-sm ml-1">
                      (${data.pnl_per_share >= 0 ? "+" : ""}{data.pnl_per_share})
                    </span>
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Duration</span>
                  <span className="text-white font-mono">{duration}</span>
                </div>
              </div>
              <div className="mt-6 pt-4 border-t border-white/10 flex items-center justify-between">
                <span className="text-xs text-gray-500">tradesignalwithai.com</span>
                <div className="flex gap-2">
                  <button
                    onClick={shareReplay}
                    className="text-xs bg-accent/20 text-accent px-3 py-1.5 rounded-lg hover:bg-accent/30 transition-colors pointer-events-auto"
                  >
                    {linkCopied ? "Copied!" : "Share Link"}
                  </button>
                  <button
                    onClick={() => { setVisibleCount(Math.max(1, data.alert_bar_index - 20)); setPlaying(true); }}
                    className="text-xs bg-white/10 text-white px-3 py-1.5 rounded-lg hover:bg-white/20 transition-colors pointer-events-auto"
                  >
                    Replay
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Chart Area ── */}
      <div ref={containerRef} className="flex-1 min-h-0" />

      {/* Persistent outcome banner — always visible through replay, great for screenshots */}
      {data.outcome && data.outcome !== "open" && (
        <div className={`absolute bottom-[68px] left-4 z-20 rounded-lg px-4 py-2.5 backdrop-blur-md border ${
          isWin ? "bg-emerald-500/15 border-emerald-500/30" : "bg-red-500/15 border-red-500/30"
        }`}>
          <div className={`flex items-center gap-3 text-sm font-bold ${isWin ? "text-emerald-400" : "text-red-400"}`}>
            <span>{isWin ? "✓" : "✖"}</span>
            <span>{outcomeLabel}</span>
            <span className="text-white/40">·</span>
            <span className="font-mono">{duration}</span>
            <span className="text-white/40">·</span>
            <span className="font-mono">
              {data.pnl_pct >= 0 ? "+" : ""}{data.pnl_pct}%
            </span>
            <span className="text-white/40">·</span>
            <span className="font-mono text-xs">
              {data.alert.symbol} {isBuy ? "LONG" : "SHORT"}
            </span>
          </div>
        </div>
      )}

      {/* ── Controls Bar ── */}
      <div className="shrink-0 bg-[#0a0f1a] border-t border-white/5 px-6 py-3">
        {/* Progress bar */}
        <div
          className="h-1.5 bg-white/5 rounded-full cursor-pointer mb-3 group"
          onClick={(e) => {
            if (!data) return;
            const rect = e.currentTarget.getBoundingClientRect();
            const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            setVisibleCount(Math.max(1, Math.round(pct * data.bars.length)));
            setPlaying(false);
          }}
        >
          <div
            className={`h-full rounded-full transition-all duration-100 ${
              phase === "target" || phase === "result"
                ? (isWin ? "bg-emerald-500" : "bg-red-500")
                : "bg-accent"
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex items-center justify-between">
          {/* Left: playback controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setVisibleCount(Math.max(1, data.alert_bar_index - 20)); setPlaying(false); }}
              className="p-1.5 rounded hover:bg-white/5 text-gray-400 transition-colors"
            >
              <SkipBack className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPlaying(!playing)}
              className="p-2.5 rounded-full bg-accent hover:bg-accent/80 text-white transition-colors"
            >
              {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <button
              onClick={() => { setVisibleCount(data.bars.length); setPlaying(false); }}
              className="p-1.5 rounded hover:bg-white/5 text-gray-400 transition-colors"
            >
              <SkipForward className="h-4 w-4" />
            </button>
          </div>

          {/* Center: alert info */}
          <div className="text-center">
            <span className="text-sm font-bold text-white">{data.alert.symbol}</span>
            <span className="text-xs text-gray-500 ml-2">{setupLabel}</span>
            <span className="text-xs text-gray-600 ml-2">Score {data.alert.score}</span>
          </div>

          {/* Right: speed + controls */}
          <div className="flex items-center gap-2">
            {[1, 2, 5].map((s) => (
              <button
                key={s}
                onClick={() => setSpeed(s)}
                className={`px-2 py-1 rounded text-xs font-bold transition-colors ${
                  speed === s ? "bg-accent/20 text-accent" : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {s}x
              </button>
            ))}
            <button
              onClick={() => setFullscreen(!fullscreen)}
              className="p-1.5 text-gray-500 hover:text-gray-300 transition-colors ml-2"
            >
              {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            </button>
            <button onClick={onClose} className="p-1.5 text-gray-500 hover:text-gray-300">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
