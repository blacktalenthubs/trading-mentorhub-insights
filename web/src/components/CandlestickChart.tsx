/** Candlestick chart using lightweight-charts v5, with MA/VWAP overlays. */

import { useEffect, useRef, Component, type ReactNode } from "react";
import { createChart, CandlestickSeries, LineSeries, ColorType } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { OHLCBar, ChartLevel } from "../api/hooks";
import { computeSMA, computeEMA, computeVWAP } from "../lib/indicators";

interface IndicatorConfig {
  key: string; // "sma20" | "sma50" | "ema9" | "vwap"
  color: string;
}

interface Props {
  data: OHLCBar[];
  levels?: ChartLevel[];
  /** User-drawn S/R lines — rendered solid + always shown (no dedup). */
  userLevels?: ChartLevel[];
  /** When true, a click on the chart calls onAddLevel with that price. */
  drawMode?: boolean;
  onAddLevel?: (price: number) => void;
  entry?: number;
  stop?: number;
  target?: number;
  height?: number;
  indicators?: IndicatorConfig[];
  hideWicks?: boolean;
  /** Direction badge in the TradePanel overlay. Defaults to "LONG" when entry > stop. */
  direction?: "LONG" | "SHORT";
  /** Show the floating Trade Panel above the chart with full level details. */
  showTradePanel?: boolean;
}

function CandlestickChartInner({
  data,
  levels = [],
  userLevels = [],
  drawMode = false,
  onAddLevel,
  entry,
  stop,
  target,
  height = 400,
  indicators = [],
  hideWicks = false,
  direction,
  showTradePanel = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);
  const priceLinesRef = useRef<any[]>([]);
  // Latest draw-mode + handler held in refs so the click subscription reads
  // current values without re-subscribing on every prop change.
  const drawModeRef = useRef(drawMode);
  const onAddLevelRef = useRef(onAddLevel);
  drawModeRef.current = drawMode;
  onAddLevelRef.current = onAddLevel;

  useEffect(() => {
    if (!containerRef.current) return;

    // If height is 0, auto-fill parent container height
    const chartHeight = height > 0 ? height : (containerRef.current.parentElement?.clientHeight || 400);

    const isLight = document.documentElement.classList.contains("light");

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: isLight ? "#ffffff" : "#050810" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.03)" },
        horzLines: { color: isLight ? "rgba(0,0,0,0.04)" : "rgba(255,255,255,0.03)" },
      },
      width: containerRef.current.clientWidth,
      height: chartHeight,
      crosshair: { mode: 1 },
      rightPriceScale: {
        autoScale: true,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        rightOffset: 5,
        minBarSpacing: 3,
      },
      // Touch + wheel zoom enabled for mobile (2026-05-26 user request).
      // Lightweight Charts default disables pinch on touch — explicitly enable.
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderDownColor: "#ef4444",
      borderUpColor: "#22c55e",
      wickDownColor: hideWicks ? "transparent" : "#ef4444",
      wickUpColor: hideWicks ? "transparent" : "#22c55e",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (containerRef.current) {
        const newHeight = height > 0 ? height : (containerRef.current.parentElement?.clientHeight || 400);
        chart.applyOptions({
          width: containerRef.current.clientWidth,
          height: newHeight,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [height, hideWicks]);

  // Update data + indicators — preserve scroll position
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current || !data.length) return;

    const chart = chartRef.current;

    // Save current visible range before updating
    const timeScale = chart.timeScale();
    const savedRange = timeScale.getVisibleLogicalRange();

    // Remove previous line series
    for (const ls of lineSeriesRefs.current) {
      try {
        chart.removeSeries(ls);
      } catch {
        // Series may already be removed if chart was re-created
      }
    }
    lineSeriesRefs.current = [];

    // Detect intraday: if multiple bars share the same date, use Unix timestamps
    const dateSet = new Set(data.map((b) => b.timestamp.split(" ")[0]));
    const isIntraday = dateSet.size < data.length;

    function toTime(ts: string): string | number {
      if (isIntraday) {
        // Convert "YYYY-MM-DD HH:MM:SS" to Unix epoch (seconds)
        return Math.floor(new Date(ts.replace(" ", "T") + "Z").getTime() / 1000);
      }
      return ts.split(" ")[0];
    }

    // Deduplicate: keep last bar per timestamp (handles duplicate dates)
    const seen = new Map<string | number, number>();
    const deduped: Array<{ time: string | number; open: number; high: number; low: number; close: number }> = [];
    for (const bar of data) {
      const t = toTime(bar.timestamp);
      if (seen.has(t)) {
        deduped[seen.get(t)!] = { time: t, open: bar.open, high: bar.high, low: bar.low, close: bar.close };
      } else {
        seen.set(t, deduped.length);
        deduped.push({ time: t, open: bar.open, high: bar.high, low: bar.low, close: bar.close });
      }
    }

    // Sort ascending by time — Lightweight Charts requires asc order
    deduped.sort((a, b) => {
      if (typeof a.time === "number" && typeof b.time === "number") return a.time - b.time;
      return String(a.time).localeCompare(String(b.time));
    });

    seriesRef.current.setData(deduped as any);

    // Compute indicators from sorted deduped data (not raw unsorted data)
    // Preserve time type (number for intraday, string for daily) so lightweight-charts stays consistent
    const closes = deduped.map((bar) => ({
      time: bar.time,
      close: bar.close,
    }));

    // For VWAP we need high/low/volume — session-anchored (last trading day)
    const sortedRaw = [...data].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    // Use the last bar's date as "today's session" (handles timezone differences)
    const lastBarDate = sortedRaw.length > 0 ? sortedRaw[sortedRaw.length - 1].timestamp.slice(0, 10) : "";
    const sessionBars = lastBarDate ? sortedRaw.filter((b) => b.timestamp.slice(0, 10) === lastBarDate) : sortedRaw;
    // Use session bars if available (intraday), otherwise all bars (daily)
    const vwapSource = sessionBars.length >= 3 ? sessionBars : sortedRaw;
    const barsForVWAP = vwapSource.map((bar) => ({
      time: toTime(bar.timestamp),
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    }));

    for (const ind of indicators) {
      let lineData: { time: string | number; value: number }[] = [];

      const smaMatch = ind.key.match(/^sma(\d+)$/);
      const emaMatch = ind.key.match(/^ema(\d+)$/);
      if (smaMatch) lineData = computeSMA(closes, parseInt(smaMatch[1]));
      else if (emaMatch) lineData = computeEMA(closes, parseInt(emaMatch[1]));
      else if (ind.key === "vwap" && sessionBars.length >= 3) {
        // VWAP only shows on today's session bars (not multi-day)
        lineData = computeVWAP(barsForVWAP);
      }

      if (lineData.length > 0) {
        // Sort ascending — Lightweight Charts requires asc order
        lineData.sort((a, b) => {
          if (typeof a.time === "number" && typeof b.time === "number") return a.time - b.time;
          return String(a.time).localeCompare(String(b.time));
        });
        const lineSeries = chart.addSeries(LineSeries, {
          color: ind.color,
          lineWidth: 1,
          crosshairMarkerVisible: false,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        lineSeries.setData(lineData as any);
        lineSeriesRefs.current.push(lineSeries);
      }
    }

    // Remove previous price lines
    for (const pl of priceLinesRef.current) {
      try {
        seriesRef.current!.removePriceLine(pl);
      } catch { /* already removed */ }
    }
    priceLinesRef.current = [];

    // Price lines — short labels + nearby-dedup.
    //
    // Old design stacked 6 long labels ("Entry $309.54", "Stop $308.18",
    // "T1/Resist $312.27", "Support $309.57", "Prior High $315.00", ...)
    // on the right edge of the price axis. When labels sit within a few
    // cents of each other they overlap and render unreadable.
    //
    // New design:
    //   1. Short 1-3 char codes (E / S / T1 / PDH / PWH / PDL / PWL)
    //   2. Sort by price descending
    //   3. Dedup: if a lower-priority label sits within DEDUP_PCT% of an
    //      already-kept label, drop it. Trade lines (E/S/T1) always win
    //      over generic levels.
    //   4. The full label text lives in the TradePanel overlay above the
    //      chart — the axis labels are just a visual marker, not the data.
    type PLine = { price: number; color: string; title: string; priority: number };
    const raw: PLine[] = [];

    // Priority: lower number wins on dedup conflict.
    if (entry)  raw.push({ price: entry,  color: "#3b82f6", title: "E",  priority: 0 });
    if (stop)   raw.push({ price: stop,   color: "#ef4444", title: "S",  priority: 0 });
    if (target) raw.push({ price: target, color: "#22c55e", title: "T1", priority: 0 });

    // Level label shortener. Maps verbose labels coming from the parent
    // to compact codes; unknown labels keep their original text.
    const shortenLabel = (label: string): string => {
      const t = label.toLowerCase();
      if (t.includes("prior") && t.includes("high")) return "PDH";
      if (t.includes("prior") && t.includes("low"))  return "PDL";
      if (t.startsWith("pwh") || (t.includes("week") && t.includes("high"))) return "PWH";
      if (t.startsWith("pwl") || (t.includes("week") && t.includes("low")))  return "PWL";
      if (t.includes("month") && t.includes("high")) return "PMH";
      if (t.includes("month") && t.includes("low"))  return "PML";
      if (t === "support" || t === "resistance")     return label[0].toUpperCase();
      if (t.includes("vwap")) return "VWAP";
      return label.length > 6 ? label.slice(0, 6) : label;
    };

    levels.forEach((lvl) => {
      raw.push({
        price: lvl.price,
        color: lvl.color,
        title: shortenLabel(lvl.label || ""),
        priority: 1,
      });
    });

    // Dedup: if two labels are within DEDUP_PCT of price, keep the one
    // with lower priority (trade lines win over level lines).
    const DEDUP_PCT = 0.3; // ±0.3% of price
    raw.sort((a, b) => a.priority - b.priority || b.price - a.price);
    const plines: PLine[] = [];
    for (const cand of raw) {
      const tooClose = plines.some(
        (kept) => Math.abs(kept.price - cand.price) / cand.price * 100 < DEDUP_PCT,
      );
      if (!tooClose) plines.push(cand);
    }

    for (const pl of plines) {
      const line = seriesRef.current!.createPriceLine({
        price: pl.price,
        color: pl.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: pl.title,
      });
      priceLinesRef.current.push(line);
    }

    // User-drawn S/R lines — solid, always shown (intentional marks, no dedup).
    for (const lvl of userLevels) {
      const line = seriesRef.current!.createPriceLine({
        price: lvl.price,
        color: lvl.color || "#94a3b8",
        lineWidth: 1,
        lineStyle: 0,  // solid
        axisLabelVisible: true,
        title: lvl.label || "S/R",
      });
      priceLinesRef.current.push(line);
    }

    // Click-to-add: in draw mode, a click sets a horizontal line at that price.
    chart.subscribeClick((param) => {
      if (!drawModeRef.current || !onAddLevelRef.current || !param.point || !seriesRef.current) return;
      const price = seriesRef.current.coordinateToPrice(param.point.y);
      if (price != null) onAddLevelRef.current(Number(price));
    });

    // Restore saved scroll position, or set initial view on first load
    if (savedRange) {
      // User had a position — restore it (just shift to include any new bars)
      timeScale.setVisibleLogicalRange(savedRange);
    } else if (data.length > 80) {
      // First load: show last 80 bars
      timeScale.setVisibleLogicalRange({ from: data.length - 80, to: data.length + 5 });
    } else {
      timeScale.fitContent();
    }
  }, [data, levels, userLevels, entry, stop, target, indicators, hideWicks]);

  // Floating trade panel — single-row overlay top-right of the chart with
  // the full Entry/Stop/Target details + R:R. Replaces the verbose
  // price-axis labels (those are now short codes E/S/T1). User can scan
  // the panel without their eyes hopping along the price scale.
  const dirGuess: "LONG" | "SHORT" = direction ?? (
    entry != null && stop != null && entry > stop ? "LONG" : "SHORT"
  );
  const rr = (entry != null && stop != null && target != null && entry !== stop)
    ? ((target - entry) / Math.abs(entry - stop)).toFixed(1)
    : null;
  const hasTrade = entry != null && stop != null && target != null;
  const showPanel = showTradePanel && hasTrade;

  // Outer wrapper must fill its parent (TradingPageV2 uses flex-1 min-h-0
  // around the chart). Without h-full here, the inner chart container has
  // no height to inherit and the chart collapses to its own intrinsic
  // height — which manifested as "chart only fills upper half" 2026-05-31.
  // Inner container is w-full h-full so it sizes correctly; the absolute-
  // positioned trade panel sits on top without taking layout space.
  return (
    <div className="w-full h-full rounded-lg relative">
      {showPanel && (
        <div
          className="absolute top-2 right-2 z-10 flex items-center gap-2 px-2.5 py-1 rounded-md border border-border-subtle bg-surface-2/95 backdrop-blur-sm text-[10px] font-mono"
          title="Trade levels"
        >
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${
              dirGuess === "LONG"
                ? "bg-bullish/20 text-bullish-text"
                : "bg-bearish/20 text-bearish-text"
            }`}
          >
            {dirGuess}
          </span>
          <span className="text-text-faint">Entry</span>
          <span className="text-accent font-semibold">${entry!.toFixed(2)}</span>
          <span className="text-text-muted">·</span>
          <span className="text-text-faint">Stop</span>
          <span className="text-bearish-text font-semibold">${stop!.toFixed(2)}</span>
          <span className="text-text-muted">·</span>
          <span className="text-text-faint">Target</span>
          <span className="text-bullish-text font-semibold">${target!.toFixed(2)}</span>
          {rr && (
            <>
              <span className="text-text-muted">·</span>
              <span className="text-text-faint">R:R</span>
              <span className="text-text-primary font-semibold">{rr}</span>
            </>
          )}
        </div>
      )}
      {drawMode && (
        <div className="absolute top-2 left-2 z-10 px-2 py-1 rounded-md bg-accent/90 text-white text-[10px] font-semibold pointer-events-none">
          Click the chart to drop a level
        </div>
      )}
      <div ref={containerRef} className={`w-full h-full ${drawMode ? "cursor-crosshair" : ""}`} />
    </div>
  );
}

/* ── Chart-specific error boundary ───────────────────────────────── */

interface ChartErrorState {
  hasError: boolean;
}

class ChartErrorBoundary extends Component<{ children: ReactNode; height?: number }, ChartErrorState> {
  constructor(props: { children: ReactNode; height?: number }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): ChartErrorState {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      const h = this.props.height ?? 400;
      return (
        <div
          className="flex flex-col items-center justify-center gap-3 rounded-lg bg-surface-2 border border-border-subtle"
          style={{ height: h }}
        >
          <p className="text-sm font-medium text-bearish-text">Chart failed to load</p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="rounded-md bg-surface-4 px-4 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-3 border border-border-subtle transition-colors"
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── Wrapped export ──────────────────────────────────────────────── */

export default function CandlestickChartWithBoundary(props: Props) {
  return (
    <ChartErrorBoundary height={props.height}>
      <CandlestickChartInner {...props} />
    </ChartErrorBoundary>
  );
}
