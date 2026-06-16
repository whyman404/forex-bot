"use client";

import * as React from "react";
import { ShieldCheck } from "lucide-react";
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
import { useAdminStepUp } from "@/hooks/admin/use-admin-totp-step-up";
import { ApiError } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Called once the operator has entered a valid code and backend has issued a token. */
  onSuccess: (stepUpToken: string) => void;
  /** Short label explaining what the operator is about to do. */
  action: string;
}

/**
 * Step-up TOTP gate for destructive admin actions. The token returned is
 * short-lived (~5 min) and must be forwarded to the next privileged API call
 * via the `X-Step-Up-TOTP` header.
 *
 * Coordinated with Argus R4 (security). Token IS NOT persisted client-side.
 */
export function TotpStepUpModal({ open, onOpenChange, onSuccess, action }: Props) {
  const stepUp = useAdminStepUp();
  const [code, setCode] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (!open) {
      setCode("");
    } else {
      // Focus after the dialog open animation so the autofocus actually lands.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      toast.error("Enter the 6-digit code from your authenticator");
      return;
    }
    try {
      const res = await stepUp.mutateAsync(code);
      onSuccess(res.step_up_token);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Invalid code");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-brand" aria-hidden="true" />
            Confirm with 2FA
          </DialogTitle>
          <DialogDescription>
            {action}. Enter your authenticator code to proceed. This action is logged.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="stepup-code">6-digit authenticator code</Label>
            <Input
              id="stepup-code"
              ref={inputRef}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              className="w-32"
              aria-describedby="stepup-help"
            />
            <p id="stepup-help" className="text-xs text-muted-foreground">
              Token is valid for about 5 minutes.
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="brand" disabled={stepUp.isPending || code.length !== 6}>
              {stepUp.isPending ? "Verifying…" : "Confirm"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
