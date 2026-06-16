"use client";

import * as React from "react";
import { toast } from "sonner";
import { AlertOctagon, ShieldAlert, ShieldOff } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TotpStepUpModal } from "@/components/admin/totp-step-up-modal";
import {
  useDisarmGlobalKill,
  useEngageGlobalKill,
  useGlobalKillStatus,
} from "@/hooks/admin/use-global-kill-switch";
import { ApiError } from "@/lib/api";

const ENGAGE_PHRASE = "ENGAGE GLOBAL KILL";
const DISARM_PHRASE = "DISARM GLOBAL KILL";

export default function GlobalKillPage() {
  const status = useGlobalKillStatus();
  const engage = useEngageGlobalKill();
  const disarm = useDisarmGlobalKill();
  const [engageOpen, setEngageOpen] = React.useState(false);
  const [disarmOpen, setDisarmOpen] = React.useState(false);
  const [engagePhrase, setEngagePhrase] = React.useState("");
  const [engageReason, setEngageReason] = React.useState("");
  const [disarmPhrase, setDisarmPhrase] = React.useState("");
  const [disarmReason, setDisarmReason] = React.useState("");
  const [stepUpFor, setStepUpFor] = React.useState<"engage" | "disarm" | null>(null);

  const armed = status.data?.state === "armed";

  async function handleEngage(token: string) {
    try {
      await engage.mutateAsync({
        body: { confirmation_phrase: engagePhrase, reason: engageReason.trim() },
        stepUpToken: token,
      });
      toast.success("Global kill engaged. All live engines are now stopped.");
      setEngageOpen(false);
      setEngagePhrase("");
      setEngageReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Engage failed");
    }
  }

  async function handleDisarm(token: string) {
    try {
      await disarm.mutateAsync({
        body: { confirmation_phrase: disarmPhrase, reason: disarmReason.trim() },
        stepUpToken: token,
      });
      toast.success("Global kill disarmed. Users must manually restart their engines.");
      setDisarmOpen(false);
      setDisarmPhrase("");
      setDisarmReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Disarm failed");
    }
  }

  return (
    <div className="space-y-4">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight text-destructive">Global kill switch</h1>
        <p className="text-sm text-muted-foreground">
          Stops every live trading engine across every user. Use only in emergencies (compromised
          credentials, broker outage with stuck orders, runaway loss).
        </p>
      </header>

      <Card className="border-destructive/40 bg-destructive/5">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
            Current state
          </CardTitle>
          <CardDescription className="text-destructive/80">
            This stops ALL live engines for ALL users. They will need to manually restart after
            disarm.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {status.isLoading || !status.data ? (
            <Skeleton className="h-24" />
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Badge variant={armed ? "destructive" : "profit"}>
                  {armed ? "ARMED" : "DISARMED"}
                </Badge>
                {status.data.live_engines_count > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {status.data.live_engines_count} live engine(s) currently running
                  </span>
                )}
              </div>
              {armed && status.data.engaged_at && (
                <p className="text-xs text-muted-foreground">
                  Engaged at{" "}
                  <time dateTime={status.data.engaged_at}>
                    {new Date(status.data.engaged_at).toLocaleString()}
                  </time>
                  {status.data.engaged_by_email && (
                    <>
                      {" "}
                      by <strong>{status.data.engaged_by_email}</strong>
                    </>
                  )}
                  {status.data.reason && (
                    <>
                      {" "}
                      — <em>{status.data.reason}</em>
                    </>
                  )}
                </p>
              )}
              {(status.data.pending_approvals?.length ?? 0) > 0 && (
                <div
                  role="status"
                  className="rounded-md border border-warn/30 bg-warn/10 p-3 text-xs"
                >
                  <p className="font-medium">Pending admin approvals</p>
                  <ul className="mt-1 space-y-0.5 text-muted-foreground">
                    {status.data.pending_approvals!.map((p) => (
                      <li key={p.admin_email}>
                        {p.admin_email} — requested {new Date(p.requested_at).toLocaleString()}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          <div className="flex flex-wrap gap-2 pt-2">
            {armed ? (
              <Button
                variant="brand"
                size="lg"
                onClick={() => setDisarmOpen(true)}
                aria-label="Disarm global kill"
              >
                <ShieldOff className="mr-2 h-5 w-5" aria-hidden="true" />
                Disarm global kill
              </Button>
            ) : (
              <Button
                variant="destructive"
                size="lg"
                onClick={() => setEngageOpen(true)}
                aria-label="Engage global kill"
              >
                <AlertOctagon className="mr-2 h-5 w-5" aria-hidden="true" />
                Engage global kill
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <Dialog open={engageOpen} onOpenChange={setEngageOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="text-destructive">Engage global kill?</DialogTitle>
            <DialogDescription>
              This stops ALL live engines for ALL users. They will need to manually restart after
              disarm. Two-step confirmation + 2FA required.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="engage-reason">Reason (required, logged)</Label>
            <Input
              id="engage-reason"
              value={engageReason}
              onChange={(e) => setEngageReason(e.target.value)}
            />
            <Label htmlFor="engage-phrase">
              Type{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">{ENGAGE_PHRASE}</code> to
              confirm
            </Label>
            <Input
              id="engage-phrase"
              value={engagePhrase}
              onChange={(e) => setEngagePhrase(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEngageOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={engagePhrase !== ENGAGE_PHRASE || engageReason.trim().length < 3}
              onClick={() => setStepUpFor("engage")}
            >
              Continue to 2FA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={disarmOpen} onOpenChange={setDisarmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disarm global kill?</DialogTitle>
            <DialogDescription>
              Users will be able to restart their live engines manually. Trades placed during the
              freeze are not retroactively applied.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="disarm-reason">Reason (required, logged)</Label>
            <Input
              id="disarm-reason"
              value={disarmReason}
              onChange={(e) => setDisarmReason(e.target.value)}
            />
            <Label htmlFor="disarm-phrase">
              Type{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">{DISARM_PHRASE}</code> to
              confirm
            </Label>
            <Input
              id="disarm-phrase"
              value={disarmPhrase}
              onChange={(e) => setDisarmPhrase(e.target.value)}
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDisarmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="brand"
              disabled={disarmPhrase !== DISARM_PHRASE || disarmReason.trim().length < 3}
              onClick={() => setStepUpFor("disarm")}
            >
              Continue to 2FA
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <TotpStepUpModal
        open={stepUpFor !== null}
        onOpenChange={(v) => !v && setStepUpFor(null)}
        action={stepUpFor === "engage" ? "Engage global kill switch" : "Disarm global kill switch"}
        onSuccess={(token) => {
          if (stepUpFor === "engage") void handleEngage(token);
          else if (stepUpFor === "disarm") void handleDisarm(token);
          setStepUpFor(null);
        }}
      />
    </div>
  );
}
