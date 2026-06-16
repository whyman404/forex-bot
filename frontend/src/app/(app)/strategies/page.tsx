"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { StrategyCard } from "@/components/strategy-card";
import { useStrategies } from "@/hooks/use-strategies";
import { ApiError } from "@/lib/api";

export default function StrategiesPage() {
  const { data, isLoading, error } = useStrategies();

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Strategies</h1>
        <p className="text-sm text-muted-foreground">
          Battle-tested strategies. Tune parameters, backtest, then go live.
        </p>
      </header>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error instanceof ApiError ? error.message : "Could not load strategies"}
        </div>
      )}

      <section aria-label="Strategy list" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {isLoading ? (
          Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-56" />)
        ) : !data || data.length === 0 ? (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">
            No strategies available yet.
          </p>
        ) : (
          data.map((s) => <StrategyCard key={s.code} strategy={s} />)
        )}
      </section>
    </div>
  );
}
