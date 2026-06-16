"use client";

import * as React from "react";
import { use } from "react";
import Link from "next/link";
import { Play, Zap, ShieldAlert, AlertOctagon } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ParamsForm, type ParamField } from "@/components/params-form";
import { HealthBadge } from "@/components/health-badge";
import { LiveTradingModal, RevertToPaperModal } from "@/components/live-trading-modal";
import { useStrategy } from "@/hooks/use-strategies";
import {
  useCreateStrategyInstance,
  useStrategyInstances,
} from "@/hooks/use-strategy-instance";
import { useBrokerAccounts } from "@/hooks/use-broker-accounts";
import {
  useInstanceHealth,
  useInstanceSignals,
  useInstanceTrades,
  useRevertToPaper,
} from "@/hooks/use-live-trading";
import { useKillInstance } from "@/hooks/use-kill-switch";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";

function fieldsFromDefaults(defaults: Record<string, unknown>): ParamField[] {
  return Object.entries(defaults).map(([key, value]) => {
    const isNumber = typeof value === "number";
    return {
      key,
      label: humanise(key),
      type: isNumber ? "number" : "text",
      step: isNumber && Number.isInteger(value) ? 1 : 0.1,
    };
  });
}

function humanise(s: string): string {
  return s
    .split(/[_\s]/)
    .map((w) => {
      const head = w.charAt(0);
      return head ? head.toUpperCase() + w.slice(1) : w;
    })
    .join(" ");
}

function isLiveInstance(riskConfig: Record<string, unknown>): boolean {
  // Backend marks a non-paper instance by `paper === false` or `live === true`
  if (typeof riskConfig.paper === "boolean") return riskConfig.paper === false;
  if (typeof riskConfig.live === "boolean") return riskConfig.live === true;
  return false;
}

export default function StrategyDetailPage({
  params,
}: {
  params: Promise<{ code: string }>;
}): React.ReactElement {
  const { code } = use(params);
  const { data, isLoading, error } = useStrategy(code);
  const brokers = useBrokerAccounts();
  const instances = useStrategyInstances();
  const create = useCreateStrategyInstance();

  const [paramValues, setParamValues] = React.useState<Record<string, number | string | boolean>>({});
  const [isLive, setIsLive] = React.useState(false);
  const [label, setLabel] = React.useState<string>("");
  const [brokerId, setBrokerId] = React.useState<string>("");
  const [liveModalOpen, setLiveModalOpen] = React.useState(false);
  const [revertModalOpen, setRevertModalOpen] = React.useState(false);

  // The strategy instance that maps to this strategy (first match wins for MVP).
  const matchingInstance = React.useMemo(() => {
    if (!instances.data || !data) return null;
    return instances.data.find((i) => i.strategy_id === data.code || i.label.includes(data.name)) ?? null;
  }, [instances.data, data]);

  const matchingInstanceIsLive = matchingInstance ? isLiveInstance(matchingInstance.risk_config) : false;

  React.useEffect(() => {
    if (data?.defaultParams) setParamValues(data.defaultParams);
    if (data?.name) setLabel(`${data.name} — paper`);
  }, [data]);

  React.useEffect(() => {
    if (brokerId) return;
    const first = brokers.data?.[0];
    if (first) setBrokerId(first.id);
  }, [brokers.data, brokerId]);

  const fields = data ? fieldsFromDefaults(data.defaultParams) : [];

  async function handleActivatePaper(): Promise<void> {
    if (!brokerId) {
      toast.error("Connect a broker before activating a strategy");
      return;
    }
    try {
      await create.mutateAsync({
        strategy_code: code,
        broker_account_id: brokerId,
        label,
        params: paramValues,
        risk_config: { paper: !isLive },
      });
      toast.success(
        isLive ? "Instance created — review and start it from Dashboard" : "Paper instance created",
      );
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not create strategy instance");
    }
  }

  if (isLoading || !data) {
    if (error) {
      return (
        <div
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
        >
          {error instanceof ApiError ? error.message : "Could not load strategy"}
        </div>
      );
    }
    return <Skeleton className="h-96" />;
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">{data.name}</h1>
            <Badge variant="outline">{data.asset}</Badge>
            <Badge variant="secondary">{data.timeframe}</Badge>
            {matchingInstanceIsLive && (
              <Badge variant="destructive" className="uppercase">
                <ShieldAlert className="mr-1 h-3 w-3" aria-hidden="true" />
                {t("live.badge")}
              </Badge>
            )}
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{data.description}</p>
        </div>
      </header>

      <Tabs defaultValue={matchingInstanceIsLive ? "live" : "config"}>
        <TabsList>
          <TabsTrigger value="config">Configuration</TabsTrigger>
          {matchingInstance && <TabsTrigger value="live">Live monitoring</TabsTrigger>}
          <TabsTrigger value="info">About</TabsTrigger>
        </TabsList>

        <TabsContent value="config" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Parameters</CardTitle>
              <CardDescription>
                Adjust strategy parameters. Backtest before going live.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <ParamsForm fields={fields} value={paramValues} onChange={setParamValues} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{matchingInstance ? "Manage instance" : "Activate"}</CardTitle>
              <CardDescription>
                {matchingInstance
                  ? "This strategy already has an instance. Go live or revert below."
                  : "Create a strategy instance. Paper mode is recommended for first runs."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {!matchingInstance && (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="label">Instance label</Label>
                      <Input
                        id="label"
                        value={label}
                        onChange={(e) => setLabel(e.target.value)}
                        placeholder="My EURUSD bot"
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="broker">Broker account</Label>
                      {brokers.isLoading ? (
                        <Skeleton className="h-10" />
                      ) : brokers.data && brokers.data.length > 0 ? (
                        <select
                          id="broker"
                          value={brokerId}
                          onChange={(e) => setBrokerId(e.target.value)}
                          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {brokers.data.map((b) => (
                            <option key={b.id} value={b.id}>
                              {b.label} ({b.account_type})
                            </option>
                          ))}
                        </select>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          No brokers yet —{" "}
                          <Link href="/broker" className="underline">
                            connect one
                          </Link>
                          .
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 border-t pt-4">
                    <div className="flex items-center gap-2">
                      <Switch
                        id="live-toggle"
                        checked={isLive}
                        onCheckedChange={setIsLive}
                        aria-describedby="live-warn"
                      />
                      <Label htmlFor="live-toggle">Live mode</Label>
                    </div>
                    {isLive && (
                      <p id="live-warn" className="text-xs text-destructive" role="alert">
                        Live mode uses real funds. Triple-check parameters first.
                      </p>
                    )}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-3">
            {matchingInstance ? (
              matchingInstanceIsLive ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => setRevertModalOpen(true)}
                  >
                    Revert to paper
                  </Button>
                  <RevertButtonWithModal
                    open={revertModalOpen}
                    onOpenChange={setRevertModalOpen}
                    instanceId={matchingInstance.id}
                    instanceLabel={matchingInstance.label}
                  />
                </>
              ) : (
                <>
                  <Button
                    variant="destructive"
                    onClick={() => setLiveModalOpen(true)}
                  >
                    <Zap className="mr-2 h-4 w-4" aria-hidden="true" />
                    Go Live
                  </Button>
                  <LiveTradingModal
                    open={liveModalOpen}
                    onOpenChange={setLiveModalOpen}
                    instanceId={matchingInstance.id}
                    instanceLabel={matchingInstance.label}
                  />
                </>
              )
            ) : (
              <Button variant="brand" onClick={handleActivatePaper} disabled={create.isPending}>
                <Play className="mr-2 h-4 w-4" aria-hidden="true" />
                {create.isPending ? "Creating…" : isLive ? "Activate" : "Activate (paper)"}
              </Button>
            )}
            <Button variant="outline" asChild>
              <Link href={`/backtest?strategy=${code}`}>Run backtest</Link>
            </Button>
          </div>
        </TabsContent>

        {matchingInstance && (
          <TabsContent value="live" className="space-y-4">
            <LiveMonitoringTab
              instanceId={matchingInstance.id}
              isLive={matchingInstanceIsLive}
            />
          </TabsContent>
        )}

        <TabsContent value="info">
          <Card>
            <CardHeader>
              <CardTitle>Default parameters</CardTitle>
              <CardDescription>Reference values from the strategy catalog.</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-y-2 text-sm">
                {Object.entries(data.defaultParams).map(([k, v]) => (
                  <React.Fragment key={k}>
                    <dt className="text-muted-foreground">{humanise(k)}</dt>
                    <dd className="text-right font-mono tabular-nums">{String(v)}</dd>
                  </React.Fragment>
                ))}
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function RevertButtonWithModal({
  open,
  onOpenChange,
  instanceId,
  instanceLabel,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instanceId: string;
  instanceLabel: string;
}): React.ReactElement {
  const revert = useRevertToPaper(instanceId);
  return (
    <RevertToPaperModal
      open={open}
      onOpenChange={onOpenChange}
      instanceLabel={instanceLabel}
      onConfirm={async (reason) => {
        await revert.mutateAsync({ reason: reason || null });
        toast.success(`Reverted ${instanceLabel} to paper mode`);
      }}
    />
  );
}

function LiveMonitoringTab({
  instanceId,
  isLive,
}: {
  instanceId: string;
  isLive: boolean;
}): React.ReactElement {
  const health = useInstanceHealth(instanceId);
  const signals = useInstanceSignals(instanceId);
  const trades = useInstanceTrades(instanceId);
  const kill = useKillInstance();
  const [confirmKill, setConfirmKill] = React.useState(false);

  async function emergencyStop(): Promise<void> {
    if (!confirmKill) {
      setConfirmKill(true);
      setTimeout(() => setConfirmKill(false), 5000);
      return;
    }
    try {
      await kill.mutateAsync({ id: instanceId, reason: "Manual emergency stop" });
      toast.success("Emergency stop executed");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not stop the instance");
    } finally {
      setConfirmKill(false);
    }
  }

  const status = health.data?.status ?? "unknown";
  const pnl = health.data?.today_pnl ?? 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2">
                Live status
                <HealthBadge
                  status={status}
                  lastHeartbeat={health.data?.last_heartbeat ?? null}
                />
              </CardTitle>
              <CardDescription>
                Auto-refreshing every 10 seconds. Pause polling by leaving this tab.
              </CardDescription>
            </div>
            <Button
              variant={confirmKill ? "destructive" : "outline"}
              onClick={emergencyStop}
              disabled={kill.isPending}
            >
              <AlertOctagon className="mr-2 h-4 w-4" aria-hidden="true" />
              {confirmKill ? "Click again to confirm" : t("live.emergency_stop")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {health.isLoading ? (
            <Skeleton className="h-20" />
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Metric label="Open positions" value={String(health.data?.open_positions ?? 0)} />
              <Metric
                label="Today P&L"
                value={new Intl.NumberFormat(undefined, {
                  style: "currency",
                  currency: "USD",
                }).format(pnl)}
                tone={pnl >= 0 ? "profit" : "loss"}
              />
              <Metric label="Today trades" value={String(health.data?.today_trades ?? 0)} />
              <Metric label="Mode" value={isLive ? "LIVE" : "Paper"} tone={isLive ? "warn" : undefined} />
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent signals</CardTitle>
          <CardDescription>Most recent signals emitted by the strategy.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {signals.isLoading ? (
            <div className="p-6">
              <Skeleton className="h-32" />
            </div>
          ) : !signals.data || signals.data.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No signals yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Asset</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead className="text-right">Acted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {signals.data.slice(0, 10).map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="text-xs">
                      {new Date(s.emitted_at).toLocaleString()}
                    </TableCell>
                    <TableCell>{s.asset}</TableCell>
                    <TableCell>
                      <Badge variant={s.side === "buy" ? "profit" : "warn"}>
                        {s.side.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{s.reason}</TableCell>
                    <TableCell className="text-right">
                      {s.acted_on ? "Yes" : "—"}
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
          <CardTitle>Recent trades</CardTitle>
          <CardDescription>Live executed trades for this instance.</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {trades.isLoading ? (
            <div className="p-6">
              <Skeleton className="h-32" />
            </div>
          ) : !trades.data || trades.data.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">No trades yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Asset</TableHead>
                  <TableHead>Side</TableHead>
                  <TableHead>Entry</TableHead>
                  <TableHead>Exit</TableHead>
                  <TableHead>P&L</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.data.slice(0, 10).map((tr) => (
                  <TableRow key={tr.id}>
                    <TableCell>{tr.asset}</TableCell>
                    <TableCell>
                      <Badge variant={tr.side === "buy" ? "profit" : "warn"}>
                        {tr.side.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{tr.entry_price}</TableCell>
                    <TableCell className="font-mono text-xs">{tr.exit_price ?? "—"}</TableCell>
                    <TableCell
                      className={
                        (tr.pnl ?? 0) >= 0 ? "text-profit font-medium" : "text-destructive font-medium"
                      }
                    >
                      {tr.pnl != null ? tr.pnl.toFixed(2) : "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{tr.status}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "profit" | "loss" | "warn";
}): React.ReactElement {
  const toneClass =
    tone === "profit"
      ? "text-profit"
      : tone === "loss"
        ? "text-destructive"
        : tone === "warn"
          ? "text-warn"
          : "text-foreground";
  return (
    <div className="space-y-1 rounded-md border bg-card p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
