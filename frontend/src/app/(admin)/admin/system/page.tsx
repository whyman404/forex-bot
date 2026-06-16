"use client";

import * as React from "react";
import {
  Activity,
  AlertCircle,
  Cpu,
  DollarSign,
  Mail,
  ShieldAlert,
  TrendingDown,
  Users,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { DependencyHealthBadge } from "@/components/admin/dependency-health-badge";
import { useAdminMetrics } from "@/hooks/admin/use-admin-metrics";
import { useAdminDepHealth } from "@/hooks/admin/use-admin-dep-health";

function formatUsdCents(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

interface KpiProps {
  label: string;
  value: string | number;
  delta?: string;
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
}

function KpiCard({ label, value, delta, icon: Icon }: KpiProps) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
          <Icon className="h-4 w-4 text-muted-foreground" aria-hidden={true} />
        </div>
        <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
        {delta && <p className="mt-1 text-xs text-muted-foreground">{delta}</p>}
      </CardContent>
    </Card>
  );
}

export default function AdminSystemPage() {
  const metrics = useAdminMetrics();
  const dep = useAdminDepHealth();

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System dashboard</h1>
          <p className="text-sm text-muted-foreground">
            KPIs, today&apos;s activity, and dependency health. Refreshes every 30 seconds.
          </p>
        </div>
        <Button asChild variant="destructive" size="sm">
          <Link href="/admin/system/global-kill">
            <ShieldAlert className="mr-2 h-4 w-4" aria-hidden="true" /> Global kill switch
          </Link>
        </Button>
      </header>

      <section aria-label="Key performance indicators">
        <h2 className="sr-only">KPIs</h2>
        {metrics.isLoading || !metrics.data ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KpiCard
              label="Total users"
              value={metrics.data.users_total.toLocaleString()}
              icon={Users}
            />
            <KpiCard
              label="Active 7d"
              value={metrics.data.users_active_7d.toLocaleString()}
              delta={`${metrics.data.users_new_7d.toLocaleString()} new in 7d`}
              icon={Activity}
            />
            <KpiCard
              label="Active subs"
              value={metrics.data.subscriptions_active.toLocaleString()}
              icon={DollarSign}
            />
            <KpiCard
              label="MRR"
              value={formatUsdCents(metrics.data.mrr_usd_cents)}
              delta={`${metrics.data.churn_30d_pct.toFixed(1)}% churn 30d`}
              icon={DollarSign}
            />
            <KpiCard
              label="Backtests today"
              value={metrics.data.today.backtests.toLocaleString()}
              icon={Cpu}
            />
            <KpiCard
              label="Signals today"
              value={metrics.data.today.signals.toLocaleString()}
              icon={Zap}
            />
            <KpiCard
              label="Trades today"
              value={metrics.data.today.trades.toLocaleString()}
              delta={`PnL ${metrics.data.today.gross_pnl_usd.toFixed(2)} USD`}
              icon={TrendingDown}
            />
            <KpiCard
              label="Live engines"
              value={metrics.data.live_engines_running.toLocaleString()}
              delta={`${metrics.data.kill_switches_armed} kill switches armed`}
              icon={ShieldAlert}
            />
          </div>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Queue depths</CardTitle>
            <CardDescription>Background jobs awaiting workers.</CardDescription>
          </CardHeader>
          <CardContent>
            {metrics.isLoading || !metrics.data ? (
              <Skeleton className="h-16" />
            ) : (
              <ul className="space-y-2 text-sm">
                <li className="flex items-center justify-between rounded-md border p-2">
                  <span className="flex items-center gap-2">
                    <Mail className="h-3.5 w-3.5" aria-hidden="true" /> Email
                  </span>
                  <span className="tabular-nums">{metrics.data.queue_depth.email}</span>
                </li>
                <li className="flex items-center justify-between rounded-md border p-2">
                  <span className="flex items-center gap-2">
                    <Cpu className="h-3.5 w-3.5" aria-hidden="true" /> Backtest
                  </span>
                  <span className="tabular-nums">{metrics.data.queue_depth.backtest}</span>
                </li>
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Dependency health</CardTitle>
            <CardDescription>Last probe per dependency.</CardDescription>
          </CardHeader>
          <CardContent>
            {dep.isLoading || !dep.data ? (
              <Skeleton className="h-32" />
            ) : dep.error ? (
              <p role="alert" className="text-sm text-destructive">
                <AlertCircle className="mr-1 inline h-4 w-4" aria-hidden="true" />
                Could not reach health endpoint.
              </p>
            ) : (
              <ul className="space-y-2 text-sm">
                {dep.data.dependencies.map((d) => (
                  <li
                    key={d.name}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2"
                  >
                    <span className="font-mono text-xs">{d.name}</span>
                    <div className="flex items-center gap-2">
                      {d.latency_ms != null && (
                        <span className="text-xs text-muted-foreground tabular-nums">
                          {d.latency_ms}ms
                        </span>
                      )}
                      <DependencyHealthBadge status={d.status} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
