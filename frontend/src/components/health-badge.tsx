"use client";

import { Activity, AlertTriangle, CircleSlash, Wifi } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HealthStatus } from "@/types";

interface HealthBadgeProps {
  status: HealthStatus;
  lastHeartbeat?: string | null;
  className?: string;
}

const VARIANTS: Record<HealthStatus, { label: string; classes: string; icon: typeof Activity }> = {
  healthy: {
    label: "Healthy",
    classes: "bg-profit/15 text-profit border-profit/30",
    icon: Activity,
  },
  degraded: {
    label: "Degraded",
    classes: "bg-warn/15 text-warn border-warn/30",
    icon: AlertTriangle,
  },
  down: {
    label: "Down",
    classes: "bg-destructive/15 text-destructive border-destructive/30",
    icon: CircleSlash,
  },
  unknown: {
    label: "Unknown",
    classes: "bg-muted text-muted-foreground border-muted-foreground/30",
    icon: Wifi,
  },
};

function formatHeartbeat(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export function HealthBadge({ status, lastHeartbeat, className }: HealthBadgeProps): React.ReactElement {
  const variant = VARIANTS[status];
  const Icon = variant.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        variant.classes,
        className,
      )}
      role="status"
      aria-label={`Strategy health: ${variant.label}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span>{variant.label}</span>
      {lastHeartbeat ? (
        <span className="text-muted-foreground/80">· {formatHeartbeat(lastHeartbeat)}</span>
      ) : null}
    </span>
  );
}
