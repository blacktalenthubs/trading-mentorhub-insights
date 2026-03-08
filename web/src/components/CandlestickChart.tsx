/** Candlestick chart using lightweight-charts v5. */

import { useEffect, useRef } from "react";
import { createChart, CandlestickSeries, ColorType } from "lightweight-charts";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { OHLCBar, ChartLevel } from "../api/hooks";

interface Props {
  data: OHLCBar[];
  levels?: ChartLevel[];
  entry?: number;
  stop?: number;
  target?: number;
  height?: number;
}

export default function CandlestickChart({
  data,
  levels = [],
  entry,
  stop,
  target,
  height = 400,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

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

  // Update data
  useEffect(() => {
    if (!seriesRef.current || !data.length) return;

    const formatted = data.map((bar) => ({
      time: bar.timestamp.split(" ")[0] as string,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
    }));

    seriesRef.current.setData(formatted as any);

    // Price lines
    const plines: Array<{ price: number; color: string; title: string }> = [];

    if (entry) plines.push({ price: entry, color: "#22c55e", title: "Entry" });
    if (stop) plines.push({ price: stop, color: "#ef4444", title: "Stop" });
    if (target) plines.push({ price: target, color: "#3b82f6", title: "Target" });

    levels.forEach((lvl) => {
      plines.push({ price: lvl.price, color: lvl.color, title: lvl.label || `$${lvl.price}` });
    });

    for (const pl of plines) {
      seriesRef.current!.createPriceLine({
        price: pl.price,
        color: pl.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: pl.title,
      });
    }

    chartRef.current?.timeScale().fitContent();
  }, [data, levels, entry, stop, target]);

  return <div ref={containerRef} className="w-full rounded-lg" />;
}
