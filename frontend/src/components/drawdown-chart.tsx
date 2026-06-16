"use client";

import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquityPoint } from "@/types";

interface DrawdownChartProps {
  data: EquityPoint[];
  height?: number;
}

export function DrawdownChart({ data, height = 220 }: DrawdownChartProps) {
  return (
    <div role="img" aria-label="Drawdown over backtest period" style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="dd" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="hsl(var(--loss))" stopOpacity={0.4} />
              <stop offset="95%" stopColor="hsl(var(--loss))" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="time"
            tickFormatter={(v: string) => v.slice(0, 10)}
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            minTickGap={32}
          />
          <YAxis
            tickFormatter={(v: number) => `${v.toFixed(0)}%`}
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            domain={["dataMin", 0]}
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--popover))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value: number) => [`${value.toFixed(2)}%`, "Drawdown"]}
            labelFormatter={(label: string) => label.slice(0, 10)}
          />
          <Area
            type="monotone"
            dataKey="drawdown"
            stroke="hsl(var(--loss))"
            fill="url(#dd)"
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
