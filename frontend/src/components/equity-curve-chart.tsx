"use client";

import * as React from "react";
import { createChart, ColorType, type IChartApi, type ISeriesApi } from "lightweight-charts";
import type { EquityPoint } from "@/types";

interface EquityCurveChartProps {
  data: EquityPoint[];
  height?: number;
}

export function EquityCurveChart({ data, height = 320 }: EquityCurveChartProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const chartRef = React.useRef<IChartApi | null>(null);
  const seriesRef = React.useRef<ISeriesApi<"Area"> | null>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: getComputedStyle(document.documentElement).getPropertyValue("--foreground"),
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: "rgba(255,255,255,0.05)" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, timeVisible: true },
      autoSize: true,
    });

    const series = chart.addAreaSeries({
      lineColor: "rgb(34, 197, 94)",
      topColor: "rgba(34, 197, 94, 0.4)",
      bottomColor: "rgba(34, 197, 94, 0.0)",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height]);

  React.useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(
      data.map((p) => ({
        time: p.time.slice(0, 10) as unknown as never, // YYYY-MM-DD
        value: p.equity,
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label="Equity curve over backtest period"
      className="w-full"
      style={{ height }}
    />
  );
}
