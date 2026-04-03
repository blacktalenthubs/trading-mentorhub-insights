/** Shared equity curve chart using lightweight-charts LineSeries. */

import { useEffect, useRef } from "react";
import { createChart, LineSeries, ColorType } from "lightweight-charts";
import type { IChartApi } from "lightweight-charts";
import type { EquityPoint } from "../types";

interface Props {
  data: EquityPoint[];
  height?: number;
  lineColor?: string;
}

export default function EquityCurve({ data, height = 200, lineColor = "#3b82f6" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0f1a" },
        textColor: "#64748b",
      },
      grid: {
        vertLines: { color: "#1a2332" },
        horzLines: { color: "#1a2332" },
      },
      width: containerRef.current.clientWidth,
      height,
      rightPriceScale: { borderColor: "#1a2332" },
      timeScale: { borderColor: "#1a2332" },
    });

    chartRef.current = chart;

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

  useEffect(() => {
    if (!chartRef.current || !data.length) return;

    // Remove previous series by recreating
    const chart = chartRef.current;

    const series = chart.addSeries(LineSeries, {
      color: lineColor,
      lineWidth: 2,
      crosshairMarkerVisible: true,
      priceFormat: { type: "custom", formatter: (v: number) => `$${v.toFixed(0)}` },
    });

    // Deduplicate: keep last point per date
    const seen = new Map<string, number>();
    const deduped: Array<{ time: string; value: number }> = [];
    for (const p of data) {
      const t = p.date as string;
      if (seen.has(t)) {
        deduped[seen.get(t)!] = { time: t, value: p.pnl };
      } else {
        seen.set(t, deduped.length);
        deduped.push({ time: t, value: p.pnl });
      }
    }

    series.setData(deduped as any);

    // Zero line
    series.createPriceLine({
      price: 0,
      color: "#475569",
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: false,
      title: "",
    });

    chart.timeScale().fitContent();

    return () => {
      try { chart.removeSeries(series); } catch { /* already removed */ }
    };
  }, [data, lineColor]);

  return <div ref={containerRef} className="w-full rounded-lg" />;
}
