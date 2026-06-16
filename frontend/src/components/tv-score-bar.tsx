"use client";

import * as React from "react";

/**
 * Horizontal composite-score bar from -100 (strong sell) to +100 (strong buy).
 *
 * A11y:
 *   - role="meter" with aria-valuemin / max / now / valuetext describing tier
 *   - Visible numeric label + tier text — colour blind users still informed
 *   - Gradient is decorative; tier text is canonical
 */

interface TVScoreBarProps {
  score: number; // -100..+100
  label?: string;
  className?: string;
}

function tierText(score: number): string {
  if (score >= 50) return "Strong Buy zone";
  if (score >= 10) return "Buy zone";
  if (score > -10) return "Neutral zone";
  if (score > -50) return "Sell zone";
  return "Strong Sell zone";
}

export function TVScoreBar({ score, label, className }: TVScoreBarProps): React.ReactElement {
  const clamped = Math.max(-100, Math.min(100, score));
  // 0..100 position from left.
  const pct = (clamped + 100) / 2;
  const tier = tierText(clamped);
  const valueText = `Composite score ${clamped.toFixed(1)} — ${tier}`;

  return (
    <div className={["space-y-1", className ?? ""].join(" ")}>
      {label && (
        <div className="flex items-baseline justify-between">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <span className="text-xs tabular-nums">
            <span className="font-semibold">{clamped.toFixed(0)}</span>
            <span className="text-muted-foreground"> / 100</span>
          </span>
        </div>
      )}
      <div
        role="meter"
        aria-valuemin={-100}
        aria-valuemax={100}
        aria-valuenow={Math.round(clamped)}
        aria-valuetext={valueText}
        aria-label={label ?? "TradingView composite score"}
        className="relative h-3 w-full overflow-hidden rounded-full border bg-muted/40"
      >
        {/* Decorative gradient: red → muted → green. Tier text is canonical. */}
        <div
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, hsl(var(--destructive) / 0.45) 0%, hsl(var(--muted-foreground) / 0.25) 50%, hsl(var(--profit, 142 76% 36%) / 0.45) 100%)",
          }}
        />
        {/* Center tick */}
        <div
          aria-hidden="true"
          className="absolute top-0 bottom-0 w-px bg-foreground/40"
          style={{ left: "50%" }}
        />
        {/* Marker */}
        <div
          aria-hidden="true"
          className="absolute top-1/2 h-4 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full border border-background bg-foreground shadow"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between text-[10px] uppercase tracking-wide text-muted-foreground">
        <span>Strong Sell</span>
        <span>Neutral</span>
        <span>Strong Buy</span>
      </div>
      {/* Always-visible tier text — keeps message understandable without colour */}
      <p className="text-xs font-medium text-foreground">{tier}</p>
    </div>
  );
}
