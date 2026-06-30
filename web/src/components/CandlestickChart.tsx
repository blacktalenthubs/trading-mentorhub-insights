/** Candlestick chart using lightweight-charts v5, with MA/VWAP overlays. */

import { useEffect, useRef, useState, Component, type ReactNode } from "react";
import { createChart, CandlestickSeries, LineSeries, HistogramSeries, createSeriesMarkers, ColorType } from "lightweight-charts";
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
  /** Volume histogram + volume MA at the bottom of the chart. */
  showVolume?: boolean;
  /** Alert markers — arrows on the bars where signals fired for this symbol. */
  alertMarkers?: { created_at: string; direction: string; grade?: string | null }[];
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
  showVolume = true,
  alertMarkers = [],
  direction,
  showTradePanel = true,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);
  const volumeSeriesRefs = useRef<any[]>([]);
  const volumeHistRef = useRef<any>(null);
  const markersApiRef = useRef<any>(null);
  const priceLinesRef = useRef<any[]>([]);
  // OHLC legend (top-left) — follows the crosshair, defaults to the latest bar.
  type Legend = { o: number; h: number; l: number; c: number; v: number; chg: number };
  const [legend, setLegend] = useState<Legend | null>(null);
  const latestLegendRef = useRef<Legend | null>(null);
  // Active-indicator legend (top-left). Only overlays that actually drew show
  // here — e.g. VWAP is dropped on multi-day/daily charts.
  const [indLegend, setIndLegend] = useState<{ key: string; color: string; label: string }[]>([]);
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
        // Smaller axis/price-line label font so the full-word trade labels
        // (Entry/Stop/Target) + level codes don't clutter the right axis.
        fontSize: 11,
      },
      grid: {
        // Clean background — no grid lines (TradingView "no grid" preference).
        vertLines: { visible: false },
        horzLines: { visible: false },
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
      // While drawing a level, freeze pan/zoom so the click registers as a
      // click (not a pan) and reliably drops the line.
      handleScale: drawModeRef.current
        ? { axisPressedMouseMove: false, mouseWheel: false, pinch: false }
        : { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      handleScroll: drawModeRef.current
        ? { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false }
        : { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
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
    markersApiRef.current = null;  // markers attach to the series; recreate on new series

    // Click-to-add (registered ONCE per chart, in the creation effect — not the
    // data effect, which re-runs every tick and would stack handlers → one click
    // firing N times). Reads draw mode + handler from refs so it stays current.
    chart.subscribeClick((param) => {
      if (!drawModeRef.current || !onAddLevelRef.current || !param.point || !seriesRef.current) return;
      const price = seriesRef.current.coordinateToPrice(param.point.y);
      if (price != null) onAddLevelRef.current(Number(price));
    });

    // OHLC legend follows the crosshair; leaving the chart restores the latest bar.
    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !seriesRef.current) { setLegend(latestLegendRef.current); return; }
      const c = param.seriesData.get(seriesRef.current) as any;
      if (!c || c.open == null) { setLegend(latestLegendRef.current); return; }
      const vol = volumeHistRef.current ? (param.seriesData.get(volumeHistRef.current) as any)?.value ?? 0 : 0;
      setLegend({ o: c.open, h: c.high, l: c.low, c: c.close, v: vol, chg: c.open ? (c.close - c.open) / c.open * 100 : 0 });
    });

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

    // Drop bars with any null/NaN OHLC. The backend now filters these, but a
    // single bad bar reaching lightweight-charts throws "Value is null" and the
    // OHLC legend's toFixed() throws on null — both take down the whole chart.
    const bars = data.filter(
      (b) =>
        Number.isFinite(b.open) &&
        Number.isFinite(b.high) &&
        Number.isFinite(b.low) &&
        Number.isFinite(b.close),
    );
    if (!bars.length) return;

    // Save current visible range before updating
    const timeScale = chart.timeScale();
    const savedRange = timeScale.getVisibleLogicalRange();

    // Remove previous line + volume series
    for (const ls of [...lineSeriesRefs.current, ...volumeSeriesRefs.current]) {
      try {
        chart.removeSeries(ls);
      } catch {
        // Series may already be removed if chart was re-created
      }
    }
    volumeSeriesRefs.current = [];
    lineSeriesRefs.current = [];

    // Detect intraday: if multiple bars share the same date, use Unix timestamps
    const dateSet = new Set(bars.map((b) => b.timestamp.split(" ")[0]));
    const isIntraday = dateSet.size < bars.length;

    function toTime(ts: string): string | number {
      if (isIntraday) {
        // Convert "YYYY-MM-DD HH:MM:SS" to Unix epoch (seconds)
        return Math.floor(new Date(ts.replace(" ", "T") + "Z").getTime() / 1000);
      }
      return ts.split(" ")[0];
    }

    // Deduplicate: keep last bar per timestamp (handles duplicate dates)
    const seen = new Map<string | number, number>();
    const deduped: Array<{ time: string | number; open: number; high: number; low: number; close: number; volume: number }> = [];
    for (const bar of bars) {
      const t = toTime(bar.timestamp);
      const row = { time: t, open: bar.open, high: bar.high, low: bar.low, close: bar.close, volume: bar.volume ?? 0 };
      if (seen.has(t)) deduped[seen.get(t)!] = row;
      else { seen.set(t, deduped.length); deduped.push(row); }
    }

    // Sort ascending by time — Lightweight Charts requires asc order
    deduped.sort((a, b) => {
      if (typeof a.time === "number" && typeof b.time === "number") return a.time - b.time;
      return String(a.time).localeCompare(String(b.time));
    });

    seriesRef.current.setData(deduped as any);

    // Default legend = latest bar (until the crosshair moves).
    if (deduped.length) {
      const lb = deduped[deduped.length - 1];
      const lg = { o: lb.open, h: lb.high, l: lb.low, c: lb.close, v: lb.volume, chg: lb.open ? (lb.close - lb.open) / lb.open * 100 : 0 };
      latestLegendRef.current = lg;
      setLegend(lg);
    }

    // Volume histogram (green up-bar / red down-bar) + 20-period volume MA in a
    // thin band at the bottom. The MA is the actionable part — bars towering over
    // it = unusually high volume (confirms breakouts / spots accumulation).
    if (showVolume && deduped.some((b) => b.volume > 0)) {
      const volSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      volSeries.setData(
        deduped.map((b) => ({
          time: b.time,
          value: b.volume,
          color: b.close >= b.open ? "rgba(34,197,94,0.45)" : "rgba(239,68,68,0.45)",
        })) as any,
      );
      volumeSeriesRefs.current.push(volSeries);
      volumeHistRef.current = volSeries;

      const VMA = 20;
      if (deduped.length >= VMA) {
        const vmaData: { time: string | number; value: number }[] = [];
        for (let i = VMA - 1; i < deduped.length; i++) {
          let sum = 0;
          for (let j = i - VMA + 1; j <= i; j++) sum += deduped[j].volume;
          vmaData.push({ time: deduped[i].time, value: sum / VMA });
        }
        const vmaSeries = chart.addSeries(LineSeries, {
          color: "#fbbf24", lineWidth: 1, priceScaleId: "volume",
          crosshairMarkerVisible: false, priceLineVisible: false, lastValueVisible: false,
        });
        vmaSeries.setData(vmaData as any);
        volumeSeriesRefs.current.push(vmaSeries);
      }
    }

    // Alert markers — arrows on the bars where signals fired for this symbol.
    {
      const markers: any[] = [];
      const numericTimes = deduped.map((b) => b.time);
      const seen = new Set<string>();
      for (const a of alertMarkers) {
        let t: string | number | null = null;
        if (isIntraday) {
          const au = Math.floor(new Date(a.created_at.replace(" ", "T")).getTime() / 1000);
          for (const bt of numericTimes) { if (typeof bt === "number" && bt <= au) t = bt; else break; }
        } else {
          const ad = a.created_at.slice(0, 10);
          if (numericTimes.includes(ad)) t = ad;
        }
        if (t == null) continue;
        const isBuy = (a.direction || "").toUpperCase() === "BUY";
        // One subtle arrow per bar per direction — no grade letters. Clusters of
        // intraday alerts on the same bar used to stack into a "↑C ↑C" column;
        // the grade still shows on each Signals-feed card.
        const key = `${t}|${isBuy ? "B" : "S"}`;
        if (seen.has(key)) continue;
        seen.add(key);
        markers.push({
          time: t,
          position: isBuy ? "belowBar" : "aboveBar",
          color: isBuy ? "rgba(34,197,94,0.6)" : "rgba(239,68,68,0.6)",
          shape: isBuy ? "arrowUp" : "arrowDown",
          text: "",
        });
      }
      markers.sort((x, y) => (typeof x.time === "number" && typeof y.time === "number" ? x.time - y.time : String(x.time).localeCompare(String(y.time))));
      try {
        if (markersApiRef.current) markersApiRef.current.setMarkers(markers);
        else markersApiRef.current = createSeriesMarkers(seriesRef.current, markers);
      } catch { /* markers best-effort */ }
    }

    // Compute indicators from sorted deduped data (not raw unsorted data)
    // Preserve time type (number for intraday, string for daily) so lightweight-charts stays consistent
    const closes = deduped.map((bar) => ({
      time: bar.time,
      close: bar.close,
    }));

    // For VWAP we need high/low/volume — session-anchored (last trading day)
    const sortedRaw = [...bars].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
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

    const drawnIndicators: { key: string; color: string; label: string }[] = [];
    for (const ind of indicators) {
      let lineData: { time: string | number; value: number }[] = [];

      const smaMatch = ind.key.match(/^sma(\d+)$/);
      const emaMatch = ind.key.match(/^ema(\d+)$/);
      // Which-line-is-which-MA label. Lives in the compact top-left legend
      // (below) instead of as a per-line value chip on the price axis — those
      // chips collided with each other and the gridlines.
      const maLabel = emaMatch ? `EMA ${emaMatch[1]}` : smaMatch ? `SMA ${smaMatch[1]}` : ind.key === "vwap" ? "VWAP" : ind.key.toUpperCase();
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
        drawnIndicators.push({ key: ind.key, color: ind.color, label: maLabel });
      }
    }
    setIndLegend(drawnIndicators);

    // RSI(14) sub-pane REMOVED 2026-06-30 — it ate ~90px of chart height and made
    // the candles hard to read on mobile, where the whole point is a fast price
    // glance when an alert fires. (Bottom Watch still ranks by RSI in its own board.)

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
    // Full words (not E/S/T codes) so traders new to the lingo read them at a glance.
    if (entry)  raw.push({ price: entry,  color: "#3b82f6", title: "Entry",  priority: 0 });
    if (stop)   raw.push({ price: stop,   color: "#ef4444", title: "Stop",   priority: 0 });
    if (target) raw.push({ price: target, color: "#22c55e", title: "Target", priority: 0 });

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

    // Restore saved scroll position, or set initial view on first load
    if (savedRange) {
      // User had a position — restore it (just shift to include any new bars)
      timeScale.setVisibleLogicalRange(savedRange);
    } else if (bars.length > 80) {
      // First load: show last 80 bars
      timeScale.setVisibleLogicalRange({ from: bars.length - 80, to: bars.length + 5 });
    } else {
      timeScale.fitContent();
    }
  }, [data, levels, userLevels, entry, stop, target, indicators, hideWicks, showVolume, alertMarkers]);

  // Toggle pan/zoom off while drawing so a click drops a level cleanly.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.applyOptions({
      handleScale: drawMode
        ? { axisPressedMouseMove: false, mouseWheel: false, pinch: false }
        : { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      handleScroll: drawMode
        ? { mouseWheel: false, pressedMouseMove: false, horzTouchDrag: false, vertTouchDrag: false }
        : { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
    });
  }, [drawMode]);

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
      {/* Top-left overlay: OHLC readout (follows crosshair) + active-indicator
          legend. The legend replaces the per-line MA value chips that used to
          stamp the price axis — same "which line is which MA" info, color-coded
          here, but the axis stays clean. */}
      {(legend || indLegend.length > 0) && (
        <div className="absolute top-2 left-2 z-10 flex flex-col gap-0.5 pointer-events-none select-none">
          {legend && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] font-mono">
              {([["O", legend.o], ["H", legend.h], ["L", legend.l], ["C", legend.c]] as const).map(([k, v]) => (
                <span key={k} className="text-text-faint">{k}<span className={`ml-0.5 ${legend.chg >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>{v.toFixed(2)}</span></span>
              ))}
              <span className={legend.chg >= 0 ? "text-bullish-text" : "text-bearish-text"}>{legend.chg >= 0 ? "+" : ""}{legend.chg.toFixed(2)}%</span>
              {legend.v > 0 && <span className="text-text-faint">Vol <span className="text-text-secondary">{legend.v >= 1e9 ? (legend.v/1e9).toFixed(2)+"B" : legend.v >= 1e6 ? (legend.v/1e6).toFixed(1)+"M" : legend.v >= 1e3 ? (legend.v/1e3).toFixed(0)+"K" : legend.v}</span></span>}
            </div>
          )}
          {indLegend.length > 0 && (
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] font-mono font-semibold">
              {indLegend.map((i) => (
                <span key={i.key} className="inline-flex items-center gap-1" style={{ color: i.color }}>
                  <span className="inline-block w-2.5 h-[2px] rounded-full" style={{ backgroundColor: i.color }} />
                  {i.label}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      {drawMode && (
        <div className="absolute top-8 left-2 z-10 px-2 py-1 rounded-md bg-accent/90 text-white text-[10px] font-semibold pointer-events-none">
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
