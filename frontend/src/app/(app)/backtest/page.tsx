"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { CalendarDays, Play, TrendingUp } from "lucide-react";
import { format, sub } from "date-fns";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/metric-card";
import { EquityCurveChart } from "@/components/equity-curve-chart";
import { DrawdownChart } from "@/components/drawdown-chart";
import { TradeTable } from "@/components/trade-table";
import { ParamsForm, type ParamField } from "@/components/params-form";
import { useStrategies } from "@/hooks/use-strategies";
import { useRunBacktest } from "@/hooks/use-backtest";
import { ApiError } from "@/lib/api";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { toTrade } from "@/types";

function MonthlyHeatmap({
  data,
}: {
  data: Array<{ year: number; month: number; return_percent: number }>;
}) {
  if (data.length === 0) {
    return (
      <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
        Monthly returns will appear after the backtest finishes.
      </p>
    );
  }
  const years = Array.from(new Set(data.map((d) => d.year))).sort();
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function cellColor(v: number | undefined): string {
    if (v === undefined) return "bg-muted";
    if (v >= 0) return "bg-profit/30 text-foreground";
    return "bg-loss/30 text-foreground";
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-muted-foreground">Year</th>
            {months.map((m) => (
              <th key={m} className="px-2 py-1 text-center text-muted-foreground">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={y}>
              <td className="px-2 py-1 font-medium">{y}</td>
              {months.map((_, idx) => {
                const cell = data.find((d) => d.year === y && d.month === idx + 1);
                return (
                  <td
                    key={idx}
                    className={`px-2 py-1 text-center tabular-nums ${cellColor(cell?.return_percent)}`}
                    title={cell ? `${cell.return_percent.toFixed(2)}%` : "no data"}
                  >
                    {cell ? cell.return_percent.toFixed(1) : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fieldsFromDefaults(defaults: Record<string, unknown> | undefined): ParamField[] {
  if (!defaults) return [];
  return Object.entries(defaults).map(([key, value]) => {
    const isNumber = typeof value === "number";
    return {
      key,
      label: key
        .split(/[_\s]/)
        .map((w) => {
          const head = w.charAt(0);
          return head ? head.toUpperCase() + w.slice(1) : w;
        })
        .join(" "),
      type: isNumber ? "number" : "text",
      step: isNumber && Number.isInteger(value) ? 1 : 0.1,
    };
  });
}

export default function BacktestPage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-[60vh]" />}>
      <BacktestPageInner />
    </React.Suspense>
  );
}

function BacktestPageInner() {
  const search = useSearchParams();
  const strategies = useStrategies();
  const runner = useRunBacktest();

  const presetStrategy = search.get("strategy") ?? undefined;
  const today = new Date();
  const oneYearAgo = sub(today, { years: 1 });

  const [strategyCode, setStrategyCode] = React.useState<string>(presetStrategy ?? "");
  const [from, setFrom] = React.useState(format(oneYearAgo, "yyyy-MM-dd"));
  const [to, setTo] = React.useState(format(today, "yyyy-MM-dd"));
  const [initialBalance, setInitialBalance] = React.useState(10000);
  const [paramValues, setParamValues] = React.useState<Record<string, number | string | boolean>>({});

  // Seed strategy + params once catalog loads.
  React.useEffect(() => {
    if (!strategies.data || strategies.data.length === 0) return;
    const candidate = strategyCode
      ? strategies.data.find((s) => s.code === strategyCode)
      : strategies.data[0];
    if (!candidate) return;
    if (!strategyCode) setStrategyCode(candidate.code);
    setParamValues(candidate.defaultParams);
  }, [strategies.data, strategyCode]);

  const selected = strategies.data?.find((s) => s.code === strategyCode);
  const fields = fieldsFromDefaults(selected?.defaultParams);

  async function handleRun() {
    if (!strategyCode) return;
    try {
      await runner.run({
        strategy_code: strategyCode,
        range_start: from,
        range_end: to,
        initial_balance: initialBalance,
        params: paramValues,
      });
      toast.success("Backtest queued — results will appear below");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start backtest");
    }
  }

  const bt = runner.backtest;
  const isInProgress = bt?.status === "queued" || bt?.status === "running";
  const isDone = bt?.status === "succeeded";
  const isFailed = bt?.status === "failed" || bt?.status === "cancelled";

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Backtest</h1>
        <p className="text-sm text-muted-foreground">
          Test strategy parameters against historical data.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5" aria-hidden="true" />
            Configuration
          </CardTitle>
          <CardDescription>Pick a strategy, date range, and parameters.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="strategy">Strategy</Label>
              {strategies.isLoading ? (
                <Skeleton className="h-10" />
              ) : (
                <select
                  id="strategy"
                  value={strategyCode}
                  onChange={(e) => setStrategyCode(e.target.value)}
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {strategies.data?.map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.name} — {s.asset}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="from">From</Label>
              <Input id="from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="to">To</Label>
              <Input id="to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="balance">Initial balance</Label>
              <Input
                id="balance"
                type="number"
                step={100}
                min={100}
                value={initialBalance}
                onChange={(e) => setInitialBalance(Number(e.target.value))}
              />
            </div>
          </div>

          {fields.length > 0 && (
            <ParamsForm fields={fields} value={paramValues} onChange={setParamValues} />
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              {selected && (
                <>
                  Asset <strong>{selected.asset}</strong> · Timeframe{" "}
                  <strong>{selected.timeframe}</strong>
                </>
              )}
            </p>
            <Button
              variant="brand"
              onClick={handleRun}
              disabled={runner.isQueueing || isInProgress || !strategyCode}
            >
              <Play className="mr-2 h-4 w-4" aria-hidden="true" />
              {runner.isQueueing ? "Queueing…" : isInProgress ? "Running…" : "Run backtest"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {runner.createError && (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {runner.createError instanceof ApiError
            ? runner.createError.message
            : "Failed to start backtest"}
        </div>
      )}

      {bt && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" aria-hidden="true" />
                Backtest {bt.id.slice(0, 8)}
              </CardTitle>
              <Badge
                variant={
                  bt.status === "succeeded"
                    ? "profit"
                    : bt.status === "failed" || bt.status === "cancelled"
                      ? "loss"
                      : "secondary"
                }
              >
                {bt.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {isInProgress && (
              <div className="space-y-3">
                <p className="text-sm text-muted-foreground">
                  Backtest is processing. Results will appear automatically.
                </p>
                <Skeleton className="h-40" />
              </div>
            )}
            {isFailed && (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                {bt.error_message ?? "Backtest failed"}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isDone && bt && (
        <section aria-label="Backtest results" className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Net profit"
              value={formatCurrency(bt.net_profit ?? 0)}
              description={`Initial ${formatCurrency(bt.initial_balance)}`}
            />
            <MetricCard
              label="Profit factor"
              value={bt.profit_factor !== null ? formatNumber(bt.profit_factor ?? 0) : "—"}
              description={`${bt.total_trades ?? 0} trades`}
            />
            <MetricCard
              label="Sharpe ratio"
              value={bt.sharpe_ratio !== null ? formatNumber(bt.sharpe_ratio ?? 0) : "—"}
              description={
                bt.metrics_extra?.sortino
                  ? `Sortino ${formatNumber(bt.metrics_extra.sortino)}`
                  : undefined
              }
            />
            <MetricCard
              label="Max drawdown"
              value={
                bt.max_drawdown_pct !== null ? formatPercent(bt.max_drawdown_pct ?? 0) : "—"
              }
              description={
                bt.win_rate_pct !== null
                  ? `Win rate ${formatPercent(bt.win_rate_pct ?? 0)}`
                  : undefined
              }
            />
          </div>

          {bt.equity_curve && bt.equity_curve.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Equity curve</CardTitle>
              </CardHeader>
              <CardContent>
                <EquityCurveChart data={bt.equity_curve} />
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            {bt.equity_curve && bt.equity_curve.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Drawdown</CardTitle>
                </CardHeader>
                <CardContent>
                  <DrawdownChart data={bt.equity_curve} />
                </CardContent>
              </Card>
            )}
            <Card>
              <CardHeader>
                <CardTitle>Monthly returns</CardTitle>
                <CardDescription>Percent per month.</CardDescription>
              </CardHeader>
              <CardContent>
                <MonthlyHeatmap data={bt.monthly_returns ?? []} />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Trades</CardTitle>
              <CardDescription>All trades from this backtest.</CardDescription>
            </CardHeader>
            <CardContent>
              <TradeTable trades={(bt.trades ?? []).map(toTrade)} />
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  );
}
