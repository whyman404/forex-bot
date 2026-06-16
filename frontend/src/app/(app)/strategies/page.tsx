"use client";

import Link from "next/link";
import { ArrowRight, Info, Play, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StrategyCard } from "@/components/strategy-card";
import { useStrategies } from "@/hooks/use-strategies";
import { ApiError } from "@/lib/api";
import type { Strategy } from "@/types";

const TV_CODE = "tv_signal";

export default function StrategiesPage() {
  const { data, isLoading, error } = useStrategies();

  // Pull tv_signal out so we can render its custom 7th card; the rest go through
  // the standard StrategyCard. If the backend hasn't shipped it yet we still
  // render a synthetic placeholder so the UI ships in lockstep with Atlas.
  const others = (data ?? []).filter((s) => s.code !== TV_CODE);
  const tvFromApi = (data ?? []).find((s) => s.code === TV_CODE) ?? null;

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
          Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-56" />)
        ) : !data || data.length === 0 ? (
          <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground sm:col-span-2 lg:col-span-3">
            No strategies available yet.
          </p>
        ) : (
          <>
            {others.map((s) => (
              <StrategyCard key={s.code} strategy={s} />
            ))}
            <TVSignalStrategyCard strategy={tvFromApi} />
          </>
        )}
      </section>
    </div>
  );
}

/**
 * Custom 7th card for the TradingView Signal strategy.
 * Has its own visual treatment (MULTI badge, MEDIUM risk, info chip) because
 * the asset and risk model do not fit the generic StrategyCard heuristics.
 */
function TVSignalStrategyCard({ strategy }: { strategy: Strategy | null }) {
  const name = strategy?.name ?? "TradingView Signal";
  return (
    <Card className="flex flex-col border-brand/40">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand" aria-hidden="true" />
            {name}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="outline">MULTI</Badge>
            <Badge variant="warn">MEDIUM</Badge>
          </div>
        </div>
        <CardDescription>
          Multi-timeframe TradingView signals → MT5 execution
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 space-y-2 text-sm">
        <p className="text-xs text-muted-foreground">
          Consensus across 5m/15m/1h/4h/1d. Threshold + agreement % gate every trade.
        </p>
        <span
          className="inline-flex items-center gap-1 rounded-md border border-warn/40 bg-warn/10 px-2 py-1 text-[11px] text-foreground"
          role="note"
        >
          <Info className="h-3 w-3" aria-hidden="true" />
          Informational signals — not financial advice
        </span>
      </CardContent>
      <CardContent className="space-y-2 pt-0">
        <Button asChild variant="brand" className="w-full">
          <Link href={`/strategies/${TV_CODE}`}>
            <Play className="mr-2 h-4 w-4" aria-hidden="true" />
            Open preview
          </Link>
        </Button>
        <Button asChild variant="outline" className="w-full">
          <Link href={`/backtest?strategy=${TV_CODE}`}>
            Backtest
            <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
