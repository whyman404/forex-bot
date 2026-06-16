"use client";

import * as React from "react";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useStrategyInstances } from "@/hooks/use-strategy-instance";
import { useKillInstance, useResetKillSwitchUi } from "@/hooks/use-kill-switch";
import { useKillSwitchStore } from "@/store/kill-switch";
import { ApiError } from "@/lib/api";

interface KillSwitchModalProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function KillSwitchModal({ open, onOpenChange }: KillSwitchModalProps) {
  const instances = useStrategyInstances();
  const killInstance = useKillInstance();
  const resetUi = useResetKillSwitchUi();
  const active = useKillSwitchStore((s) => s.active);
  const reasonStored = useKillSwitchStore((s) => s.reason);

  const [confirm, setConfirm] = React.useState("");
  const [reason, setReason] = React.useState("");

  const liveInstances = (instances.data ?? []).filter((i) =>
    ["running", "paused", "errored"].includes(i.status),
  );

  const canTrigger =
    confirm === "KILL" && reason.trim().length >= 3 && liveInstances.length > 0;

  async function handleTrigger() {
    if (!canTrigger) return;
    try {
      await Promise.all(
        liveInstances.map((inst) =>
          killInstance.mutateAsync({ id: inst.id, reason: reason.trim() }),
        ),
      );
      toast.success(`Killed ${liveInstances.length} instance(s)`);
      setConfirm("");
      setReason("");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Failed to kill instances");
    }
  }

  function handleReset() {
    resetUi();
    toast.success("Kill banner cleared. Re-enable strategies manually.");
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            Emergency kill switch
          </DialogTitle>
          <DialogDescription>
            This stops every running strategy instance immediately. Open positions remain — close
            them in your broker terminal if required.
          </DialogDescription>
        </DialogHeader>

        {active ? (
          <div className="space-y-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
            <p className="font-medium text-destructive">Kill banner is active.</p>
            {reasonStored && (
              <p>
                <span className="text-muted-foreground">Last reason:</span> {reasonStored}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Clearing the banner does not restart any strategy.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Instances that will be killed</Label>
              {instances.isLoading ? (
                <Skeleton className="h-16" />
              ) : liveInstances.length === 0 ? (
                <p className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                  No running or paused instances. Nothing to kill.
                </p>
              ) : (
                <ul className="space-y-1.5 rounded-md border p-2 text-sm">
                  {liveInstances.map((i) => (
                    <li key={i.id} className="flex items-center justify-between gap-2">
                      <span className="truncate">{i.label}</span>
                      <Badge variant={i.status === "running" ? "profit" : "warn"}>
                        {i.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kill-reason">Reason (required)</Label>
              <Input
                id="kill-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. unexpected drawdown, news event"
                autoComplete="off"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="kill-confirm">
                Type <span className="font-mono">KILL</span> to confirm
              </Label>
              <Input
                id="kill-confirm"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {active ? (
            <Button variant="destructive" onClick={handleReset}>
              Clear banner
            </Button>
          ) : (
            <Button
              variant="destructive"
              onClick={handleTrigger}
              disabled={!canTrigger || killInstance.isPending}
            >
              {killInstance.isPending ? "Killing…" : "Activate kill switch"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
