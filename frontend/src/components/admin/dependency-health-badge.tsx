import { Activity, AlertTriangle, CircleSlash, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { DependencyStatus } from "@/types/admin";

interface Props {
  status: DependencyStatus;
  className?: string;
}

const STATUS: Record<
  DependencyStatus,
  { label: string; classes: string; icon: typeof Activity }
> = {
  up: {
    label: "Up",
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
    icon: HelpCircle,
  },
};

export function DependencyHealthBadge({ status, className }: Props) {
  const s = STATUS[status] ?? STATUS.unknown;
  const Icon = s.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        s.classes,
        className,
      )}
      role="status"
      aria-label={`Dependency status: ${s.label}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span>{s.label}</span>
    </span>
  );
}
