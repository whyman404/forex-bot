"use client";

import * as React from "react";
import { toast } from "sonner";
import { AlertTriangle, Edit3, ShieldAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TotpStepUpModal } from "@/components/admin/totp-step-up-modal";
import {
  useAdminKillAllStrategyInstances,
  useAdminStrategies,
  useAdminUpdateStrategy,
} from "@/hooks/admin/use-admin-strategies";
import { ApiError } from "@/lib/api";
import type { AdminStrategy, StrategyRiskRating } from "@/types/admin";

export default function AdminStrategiesPage() {
  const strategies = useAdminStrategies();
  const update = useAdminUpdateStrategy();
  const killAll = useAdminKillAllStrategyInstances();
  const [editTarget, setEditTarget] = React.useState<AdminStrategy | null>(null);
  const [paramsJson, setParamsJson] = React.useState("");
  const [killTarget, setKillTarget] = React.useState<AdminStrategy | null>(null);
  const [killConfirm, setKillConfirm] = React.useState("");
  const [killReason, setKillReason] = React.useState("");
  const [killStepUpOpen, setKillStepUpOpen] = React.useState(false);

  function openEdit(s: AdminStrategy) {
    setEditTarget(s);
    setParamsJson(JSON.stringify(s.default_params, null, 2));
  }

  async function saveParams() {
    if (!editTarget) return;
    try {
      const parsed = JSON.parse(paramsJson);
      await update.mutateAsync({
        id: editTarget.id,
        body: { default_params: parsed },
      });
      toast.success("Default params updated.");
      setEditTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Invalid params");
    }
  }

  async function toggleEnabled(s: AdminStrategy, enabled: boolean) {
    try {
      await update.mutateAsync({ id: s.id, body: { enabled } });
      toast.success(`${s.name} ${enabled ? "enabled" : "disabled"}.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Update failed");
    }
  }

  async function changeRisk(s: AdminStrategy, rating: StrategyRiskRating) {
    try {
      await update.mutateAsync({ id: s.id, body: { risk_rating: rating } });
      toast.success(`Risk rating set to ${rating}.`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Update failed");
    }
  }

  async function handleKillAll(stepUpToken: string) {
    if (!killTarget) return;
    try {
      const res = await killAll.mutateAsync({
        id: killTarget.id,
        reason: killReason.trim(),
        stepUpToken,
      });
      toast.success(`Killed ${res.killed} instance(s) of ${killTarget.name}.`);
      setKillTarget(null);
      setKillConfirm("");
      setKillReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Kill failed");
    }
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Strategies</h1>
        <p className="text-sm text-muted-foreground">
          Enable/disable, tune risk ratings, edit defaults, or emergency-kill all instances.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-semibold">Catalog</CardTitle>
        </CardHeader>
        <CardContent>
          {strategies.isLoading ? (
            <Skeleton className="h-48" />
          ) : !strategies.data ? (
            <p className="text-sm text-muted-foreground">No strategies found.</p>
          ) : (
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Strategy</TableHead>
                    <TableHead>Enabled</TableHead>
                    <TableHead>Risk</TableHead>
                    <TableHead className="text-right">Instances</TableHead>
                    <TableHead className="text-right">Running</TableHead>
                    <TableHead className="w-12 text-right">
                      <span className="sr-only">Actions</span>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {strategies.data.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-sm font-medium">{s.name}</span>
                          <span className="font-mono text-xs text-muted-foreground">{s.code}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Switch
                          checked={s.enabled}
                          aria-label={`Toggle ${s.name}`}
                          onCheckedChange={(v) => toggleEnabled(s, v)}
                        />
                      </TableCell>
                      <TableCell>
                        <select
                          value={s.risk_rating}
                          onChange={(e) => changeRisk(s, e.target.value as StrategyRiskRating)}
                          className="h-9 rounded-md border bg-background px-2 text-xs"
                          aria-label={`Risk rating for ${s.name}`}
                        >
                          <option value="low">low</option>
                          <option value="medium">medium</option>
                          <option value="high">high</option>
                          <option value="extreme">extreme</option>
                        </select>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{s.instances_count}</TableCell>
                      <TableCell className="text-right">
                        <Badge variant={s.running_count > 0 ? "profit" : "outline"}>
                          {s.running_count}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEdit(s)}
                            aria-label={`Edit params for ${s.name}`}
                          >
                            <Edit3 className="h-4 w-4" aria-hidden="true" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setKillTarget(s)}
                            aria-label={`Kill all instances of ${s.name}`}
                            disabled={s.running_count === 0}
                          >
                            <ShieldAlert className="h-4 w-4 text-destructive" aria-hidden="true" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={!!editTarget} onOpenChange={(v) => !v && setEditTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit default params — {editTarget?.name}</DialogTitle>
            <DialogDescription>
              JSON object. Changes apply to NEW instances only. Existing instances keep their
              committed params.
            </DialogDescription>
          </DialogHeader>
          <textarea
            value={paramsJson}
            onChange={(e) => setParamsJson(e.target.value)}
            rows={12}
            className="w-full rounded-md border bg-background p-2 font-mono text-xs"
            aria-label="Default params JSON"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              Cancel
            </Button>
            <Button variant="brand" onClick={saveParams} disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!killTarget} onOpenChange={(v) => !v && setKillTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              Kill all instances of {killTarget?.name}?
            </DialogTitle>
            <DialogDescription>
              This stops {killTarget?.running_count} running instance(s) immediately. Open positions
              are NOT closed automatically. Users will need to manually restart.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="kill-reason-strat">Reason (required, logged)</Label>
            <Input
              id="kill-reason-strat"
              value={killReason}
              onChange={(e) => setKillReason(e.target.value)}
              placeholder="e.g. critical bug discovered"
            />
            <Label htmlFor="kill-confirm-strat">
              Type <code className="rounded bg-muted px-1 py-0.5 text-xs">KILL-ALL</code> to confirm
            </Label>
            <Input
              id="kill-confirm-strat"
              value={killConfirm}
              onChange={(e) => setKillConfirm(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setKillTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={killConfirm !== "KILL-ALL" || killReason.trim().length < 3}
              onClick={() => setKillStepUpOpen(true)}
            >
              Continue to 2FA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TotpStepUpModal
        open={killStepUpOpen}
        onOpenChange={setKillStepUpOpen}
        action={`Kill all instances of ${killTarget?.name}`}
        onSuccess={(token) => {
          void handleKillAll(token);
        }}
      />
    </div>
  );
}
