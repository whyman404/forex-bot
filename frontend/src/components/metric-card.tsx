import * as React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, pnlClass } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: number;
  description?: string;
  icon?: React.ReactNode;
  className?: string;
}

export function MetricCard({ label, value, delta, description, icon, className }: MetricCardProps) {
  return (
    <Card className={cn("animate-fade-in", className)}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        {icon ? (
          <div className="text-muted-foreground" aria-hidden="true">
            {icon}
          </div>
        ) : null}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tabular-nums">{value}</div>
        {typeof delta === "number" && (
          <p className={cn("text-xs", pnlClass(delta))}>
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(2)}%
          </p>
        )}
        {description && (
          <CardDescription className="mt-1 text-xs">{description}</CardDescription>
        )}
      </CardContent>
    </Card>
  );
}
