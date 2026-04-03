/** Candlestick chart using lightweight-charts v5, with MA/VWAP overlays. */

import { useEffect, useRef } from "react";
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
  entry?: number;
  stop?: number;
  target?: number;
  height?: number;
  indicators?: IndicatorConfig[];
}

export default function CandlestickChart({
  data,
  levels = [],
  entry,
  stop,
  target,
  height = 400,
  indicators = [],
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);
  const priceLinesRef = useRef<any[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0a0a" },
        textColor: "#9ca3af",
      },
      grid: {
        vertLines: { color: "#1f2937" },
        horzLines: { color: "#1f2937" },
      },
      width: containerRef.current.clientWidth,
      height,
      crosshair: { mode: 0 },
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
  }, [height]);

  // Update data + indicators
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current || !data.length) return;

    const chart = chartRef.current;

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
    const closes = deduped.map((bar) => ({
      time: String(bar.time),
      close: bar.close,
    }));

    // For VWAP we need high/low/volume — rebuild from sorted raw data
    const sortedRaw = [...data].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const barsForVWAP = sortedRaw.map((bar) => ({
      time: toTime(bar.timestamp) as string,
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
      else if (ind.key === "vwap") lineData = computeVWAP(barsForVWAP);

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

    // Price lines
    const plines: Array<{ price: number; color: string; title: string }> = [];

    if (entry) plines.push({ price: entry, color: "#22c55e", title: "Entry" });
    if (stop) plines.push({ price: stop, color: "#ef4444", title: "Stop" });
    if (target) plines.push({ price: target, color: "#3b82f6", title: "Target" });

    levels.forEach((lvl) => {
      plines.push({ price: lvl.price, color: lvl.color, title: lvl.label || `$${lvl.price}` });
    });

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

    chart.timeScale().fitContent();
  }, [data, levels, entry, stop, target, indicators]);

  return <div ref={containerRef} className="w-full rounded-lg" />;
}
