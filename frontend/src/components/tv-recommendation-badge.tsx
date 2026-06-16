"use client";

import * as React from "react";
import { ArrowUp, ArrowDown, Minus, ArrowUpRight, ArrowDownRight } from "lucide-react";
import type { TVRecommendation } from "@/types";

/**
 * Accessible TV recommendation badge.
 *
 * A11y contract: recommendation is conveyed via:
 *   1. Visible TEXT label (STRONG BUY, BUY, NEUTRAL, SELL, STRONG SELL)
 *   2. Distinct ICON per tier (double-arrow for strong, single for normal)
 *   3. COLOR token (profit / warn / muted / destructive)
 * Never via color alone — colour-blind users still get text + glyph.
 */

interface TVRecommendationBadgeProps {
  recommendation: TVRecommendation;
  size?: "sm" | "md";
  /** Optional override label (e.g. "STRONG BUY (1h)") */
  label?: string;
  className?: string;
}

const META: Record<
  TVRecommendation,
  {
    text: string;
    Icon: typeof ArrowUp;
    bg: string;
    fg: string;
    border: string;
  }
> = {
  STRONG_BUY: {
    text: "STRONG BUY",
    Icon: ArrowUp,
    bg: "bg-profit/15",
    fg: "text-profit",
    border: "border-profit/40",
  },
  BUY: {
    text: "BUY",
    Icon: ArrowUpRight,
    bg: "bg-profit/10",
    fg: "text-profit",
    border: "border-profit/30",
  },
  NEUTRAL: {
    text: "NEUTRAL",
    Icon: Minus,
    bg: "bg-muted",
    fg: "text-muted-foreground",
    border: "border-border",
  },
  SELL: {
    text: "SELL",
    Icon: ArrowDownRight,
    bg: "bg-destructive/10",
    fg: "text-destructive",
    border: "border-destructive/30",
  },
  STRONG_SELL: {
    text: "STRONG SELL",
    Icon: ArrowDown,
    bg: "bg-destructive/15",
    fg: "text-destructive",
    border: "border-destructive/40",
  },
};

export function TVRecommendationBadge({
  recommendation,
  size = "md",
  label,
  className,
}: TVRecommendationBadgeProps): React.ReactElement {
  const meta = META[recommendation];
  const sizing =
    size === "sm"
      ? "px-1.5 py-0.5 text-[10px] gap-1"
      : "px-2 py-1 text-xs gap-1.5";
  return (
    <span
      className={[
        "inline-flex items-center rounded-md border font-semibold tracking-wide uppercase",
        meta.bg,
        meta.fg,
        meta.border,
        sizing,
        className ?? "",
      ].join(" ")}
      // The text content is already readable; we still set aria-label so screen
      // readers announce the full tier even if a translation strips the icon.
      aria-label={`TradingView recommendation: ${label ?? meta.text}`}
      role="status"
    >
      <meta.Icon
        className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"}
        aria-hidden="true"
      />
      <span>{label ?? meta.text}</span>
    </span>
  );
}
