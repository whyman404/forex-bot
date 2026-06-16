import Link from "next/link";
import { ArrowRight, Play } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatPercent, formatNumber } from "@/lib/utils";
import type { Strategy } from "@/types";

interface StrategyCardProps {
  strategy: Strategy;
}

function riskLabel(s: Strategy): { label: string; tone: "profit" | "warn" | "loss" } {
  const tf = s.timeframe.toUpperCase();
  if (tf === "M1" || tf === "M5") return { label: "Aggressive", tone: "loss" };
  if (tf === "M15" || tf === "M30") return { label: "Balanced", tone: "warn" };
  return { label: "Conservative", tone: "profit" };
}

export function StrategyCard({ strategy }: StrategyCardProps) {
  const risk = riskLabel(strategy);
  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>{strategy.name}</CardTitle>
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="outline">{strategy.asset}</Badge>
            <Badge variant={risk.tone}>{risk.label}</Badge>
          </div>
        </div>
        <CardDescription className="line-clamp-2">{strategy.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex-1 space-y-2 text-sm">
        <dl className="grid grid-cols-2 gap-y-1.5">
          <dt className="text-muted-foreground">Timeframe</dt>
          <dd className="text-right tabular-nums">{strategy.timeframe}</dd>
          {strategy.metrics && (
            <>
              <dt className="text-muted-foreground">Win rate</dt>
              <dd className="text-right tabular-nums">
                {formatPercent(strategy.metrics.winRate)}
              </dd>
              <dt className="text-muted-foreground">Profit factor</dt>
              <dd className="text-right tabular-nums">
                {formatNumber(strategy.metrics.profitFactor)}
              </dd>
              <dt className="text-muted-foreground">Max DD</dt>
              <dd className="text-right tabular-nums">
                {formatPercent(strategy.metrics.maxDrawdown)}
              </dd>
            </>
          )}
        </dl>
      </CardContent>
      <CardContent className="space-y-2 pt-0">
        <Button asChild variant="brand" className="w-full">
          <Link href={`/backtest?strategy=${strategy.code}`}>
            <Play className="mr-2 h-4 w-4" aria-hidden="true" />
            Backtest
          </Link>
        </Button>
        <Button asChild variant="outline" className="w-full">
          <Link href={`/strategies/${strategy.code}`}>
            View detail
            <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
