"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Activity, BarChart3, Bell, DollarSign, Sparkles, Wallet } from "lucide-react";
import { format } from "date-fns";
import { MetricCard } from "@/components/metric-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMe } from "@/hooks/use-me";
import {
  useDashboardBacktests,
  useDashboardInstances,
  useDashboardUnreadNotifications,
} from "@/hooks/use-dashboard";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/utils";

export default function DashboardPage() {
  const me = useMe();
  const instances = useDashboardInstances();
  const backtests = useDashboardBacktests(5);
  const unread = useDashboardUnreadNotifications();
  const searchParams = useSearchParams();

  React.useEffect(() => {
    // Surfaced when middleware redirected a non-admin from /admin/*.
    if (searchParams.get("admin_denied") === "1") {
      toast.error("Admin access required.");
    }
  }, [searchParams]);

  const activeStrategies =
    instances.data?.filter((s) => s.status === "running").length ?? 0;
  const backtestCount = backtests.data?.length ?? 0;
  // Net PnL across recently completed backtests as a rough "performance" proxy.
  const recentNetProfit =
    backtests.data?.reduce((acc, b) => acc + (b.net_profit ?? 0), 0) ?? 0;

  const allLoading = me.isLoading || instances.isLoading || backtests.isLoading;

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          {me.data?.display_name
            ? `Welcome back, ${me.data.display_name}.`
            : "A live snapshot of your trading activity."}
        </p>
      </header>

      <section
        aria-label="Performance summary"
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {allLoading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        ) : (
          <>
            <MetricCard
              label="Account balance"
              value={formatCurrency(0)}
              description="Connect a broker to see live balance"
              icon={<Wallet className="h-4 w-4" />}
            />
            <MetricCard
              label="Active strategies"
              value={activeStrategies.toString()}
              description={`${instances.data?.length ?? 0} total configured`}
              icon={<Sparkles className="h-4 w-4" />}
            />
            <MetricCard
              label="Backtests (recent)"
              value={backtestCount.toString()}
              description={
                recentNetProfit !== 0
                  ? `Net ${formatCurrency(recentNetProfit)} across recent runs`
                  : "Run your first backtest"
              }
              delta={recentNetProfit !== 0 ? (recentNetProfit > 0 ? 1 : -1) : undefined}
              icon={<BarChart3 className="h-4 w-4" />}
            />
            <MetricCard
              label="Unread alerts"
              value={(unread.data?.length ?? 0).toString()}
              description={unread.data?.[0]?.title ?? "All clear"}
              icon={<Bell className="h-4 w-4" />}
            />
          </>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5" aria-hidden="true" />
                  Recent backtests
                </CardTitle>
                <CardDescription>Your five most recent backtest runs.</CardDescription>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href="/backtest">New backtest</Link>
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {backtests.isLoading ? (
              <Skeleton className="h-40" />
            ) : !backtests.data || backtests.data.length === 0 ? (
              <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                No backtests yet. Pick a strategy and run your first backtest.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Created</TableHead>
                    <TableHead>Range</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Net P&amp;L</TableHead>
                    <TableHead className="text-right">PF</TableHead>
                    <TableHead className="text-right">Win%</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {backtests.data.map((bt) => (
                    <TableRow key={bt.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {format(new Date(bt.created_at), "MMM dd, HH:mm")}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs">
                        {bt.range_start} → {bt.range_end}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(bt.status)}>{bt.status}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {bt.net_profit !== null && bt.net_profit !== undefined
                          ? formatCurrency(bt.net_profit)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {bt.profit_factor !== null && bt.profit_factor !== undefined
                          ? formatNumber(bt.profit_factor)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {bt.win_rate_pct !== null && bt.win_rate_pct !== undefined
                          ? formatPercent(bt.win_rate_pct)
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="link" size="sm">
                          <Link href={`/backtest?id=${bt.id}`}>View</Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" aria-hidden="true" />
              Active strategies
            </CardTitle>
            <CardDescription>Running and paused instances.</CardDescription>
          </CardHeader>
          <CardContent>
            {instances.isLoading ? (
              <Skeleton className="h-40" />
            ) : !instances.data || instances.data.length === 0 ? (
              <p className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
                No strategy instances yet.{" "}
                <Link href="/strategies" className="underline">
                  Browse strategies
                </Link>
                .
              </p>
            ) : (
              <ul className="space-y-3">
                {instances.data.slice(0, 6).map((inst) => (
                  <li key={inst.id} className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{inst.label}</p>
                      <p className="text-xs text-muted-foreground">
                        Updated {format(new Date(inst.updated_at), "MMM dd, HH:mm")}
                      </p>
                    </div>
                    <Badge variant={instanceStatusVariant(inst.status)}>{inst.status}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5" aria-hidden="true" />
            Get started
          </CardTitle>
          <CardDescription>One path to first profit.</CardDescription>
        </CardHeader>
        <CardContent>
          <ol className="grid gap-3 sm:grid-cols-3">
            <li className="rounded-md border p-3">
              <p className="text-xs font-semibold text-muted-foreground">Step 1</p>
              <p className="mt-1 text-sm font-medium">Pick a strategy</p>
              <Button asChild variant="link" size="sm" className="mt-2 px-0">
                <Link href="/strategies">Browse strategies →</Link>
              </Button>
            </li>
            <li className="rounded-md border p-3">
              <p className="text-xs font-semibold text-muted-foreground">Step 2</p>
              <p className="mt-1 text-sm font-medium">Backtest it</p>
              <Button asChild variant="link" size="sm" className="mt-2 px-0">
                <Link href="/backtest">Run backtest →</Link>
              </Button>
            </li>
            <li className="rounded-md border p-3">
              <p className="text-xs font-semibold text-muted-foreground">Step 3</p>
              <p className="mt-1 text-sm font-medium">Connect broker</p>
              <Button asChild variant="link" size="sm" className="mt-2 px-0">
                <Link href="/broker">Connect MT5 →</Link>
              </Button>
            </li>
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

function statusVariant(s: string): "outline" | "profit" | "loss" | "secondary" {
  if (s === "succeeded") return "profit";
  if (s === "failed" || s === "cancelled") return "loss";
  return "secondary";
}

function instanceStatusVariant(s: string): "outline" | "profit" | "loss" | "secondary" | "warn" {
  if (s === "running") return "profit";
  if (s === "killed" || s === "errored") return "loss";
  if (s === "paused") return "warn";
  return "secondary";
}

export const dynamic = "force-dynamic";
