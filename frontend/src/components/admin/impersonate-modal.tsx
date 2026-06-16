"use client";

import * as React from "react";
import { AlertTriangle, UserCog } from "lucide-react";
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
import { useAdminImpersonate } from "@/hooks/admin/use-admin-users";
import { ApiError } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  userId: string;
  userEmail: string;
  stepUpToken: string;
}

/**
 * Impersonation modal. Requires a step-up TOTP token; the calling page is
 * responsible for collecting it via TotpStepUpModal first. On success, opens
 * a new tab carrying the impersonation access token via the URL hash so it
 * never persists in browser history or server logs.
 */
export function ImpersonateModal({
  open,
  onOpenChange,
  userId,
  userEmail,
  stepUpToken,
}: Props) {
  const impersonate = useAdminImpersonate();
  const [reason, setReason] = React.useState("");

  async function handleConfirm() {
    if (reason.trim().length < 5) {
      toast.error("Reason must be at least 5 characters — this is logged.");
      return;
    }
    try {
      const res = await impersonate.mutateAsync({
        id: userId,
        stepUpToken,
        reason: reason.trim(),
      });
      // Open a clean tab with the token in the URL hash so it never travels
      // through the network as a query string and is not stored in history.
      const url = `/impersonate#token=${encodeURIComponent(res.access_token)}`;
      window.open(url, "_blank", "noopener,noreferrer");
      toast.success(`Impersonation session opened (audit ${res.audit_log_id}).`);
      onOpenChange(false);
      setReason("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not start impersonation");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserCog className="h-5 w-5" aria-hidden="true" />
            Impersonate {userEmail}
          </DialogTitle>
          <DialogDescription>
            You will see the app AS THIS USER in a new tab. Your admin session pauses for that tab.
            Actions log under both IDs.
          </DialogDescription>
        </DialogHeader>
        <div
          className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive"
          role="alert"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Admin actions are logged. Do not impersonate without justification. Trades placed during
            impersonation count against the user&apos;s account.
          </p>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="imp-reason">Reason (required, logged)</Label>
          <Input
            id="imp-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. SUP-1492 troubleshooting backtest failure"
            autoComplete="off"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={impersonate.isPending || reason.trim().length < 5}
          >
            {impersonate.isPending ? "Opening…" : "Open impersonated session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
