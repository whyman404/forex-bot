"use client";

import Link from "next/link";
import { CheckCircle2, Circle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LiveGateCheck } from "@/types";

interface GateCheckListProps {
  gates: LiveGateCheck[];
  className?: string;
  /** Use `loading` to render skeleton-like rows. */
  loading?: boolean;
}

/**
 * Reusable safety-gate checklist. Renders one row per gate with ✓ / ✗ icons,
 * a short label, optional detail line, and a "Fix" link when the gate fails
 * and a `fix_url` is supplied.
 */
export function GateCheckList({ gates, className, loading }: GateCheckListProps): React.ReactElement {
  if (loading) {
    return (
      <ul className={cn("space-y-2", className)}>
        {Array.from({ length: 6 }).map((_, i) => (
          <li
            key={i}
            className="flex h-10 animate-pulse items-center gap-3 rounded-md border bg-muted/40 px-3"
          />
        ))}
      </ul>
    );
  }
  return (
    <ul className={cn("space-y-2", className)} aria-label="Live trading eligibility checks">
      {gates.map((gate) => (
        <li
          key={gate.id}
          className={cn(
            "flex items-start gap-3 rounded-md border p-3 text-sm",
            gate.passed ? "border-profit/30 bg-profit/5" : "border-destructive/30 bg-destructive/5",
          )}
        >
          {gate.passed ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-profit" aria-hidden="true" />
          ) : (
            <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
          )}
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-medium">{gate.label}</span>
              <span className="sr-only">{gate.passed ? "passed" : "not yet passed"}</span>
            </div>
            {gate.detail ? (
              <p className="mt-0.5 text-xs text-muted-foreground">{gate.detail}</p>
            ) : null}
          </div>
          {!gate.passed && gate.fix_url ? (
            <Link
              href={gate.fix_url}
              className="rounded-md border border-destructive/40 px-2 py-1 text-xs font-medium text-destructive hover:bg-destructive/10"
            >
              Fix
            </Link>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** Used in compact summary rows e.g. on the live monitoring tab. */
export function GateSummary({ passed, total }: { passed: number; total: number }): React.ReactElement {
  const pct = total > 0 ? Math.round((passed / total) * 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <Circle
        className={cn(
          "h-3 w-3",
          pct === 100 ? "text-profit" : pct >= 60 ? "text-warn" : "text-destructive",
        )}
        aria-hidden="true"
      />
      <span>
        {passed} / {total} gates passed
      </span>
    </div>
  );
}
