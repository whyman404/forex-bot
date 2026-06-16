"use client";

import * as React from "react";
import { Copy, KeyRound } from "lucide-react";
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

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  tempPassword: string | null;
  expiresAt: string | null;
  userEmail: string;
}

/**
 * One-time display of a reset password. The plaintext value is NEVER stored or
 * logged client-side, and the modal closes only via the explicit "Done" button
 * so the operator must acknowledge they have captured it.
 */
export function ResetPasswordResultModal({
  open,
  onOpenChange,
  tempPassword,
  expiresAt,
  userEmail,
}: Props) {
  const [confirmed, setConfirmed] = React.useState(false);

  React.useEffect(() => {
    if (open) setConfirmed(false);
  }, [open]);

  async function copy() {
    if (!tempPassword) return;
    try {
      await navigator.clipboard.writeText(tempPassword);
      toast.success("Temporary password copied to clipboard");
    } catch {
      toast.error("Clipboard unavailable — copy manually");
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        // Don't allow closing by overlay click — operator must press Done.
        if (!v && !confirmed) return;
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-brand">
            <KeyRound className="h-5 w-5" aria-hidden="true" />
            Temporary password
          </DialogTitle>
          <DialogDescription>
            This will be shown only once for <span className="font-mono">{userEmail}</span>. Copy it
            now and deliver it to the user out-of-band. We do not store the plaintext.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div
            className="rounded-md border bg-muted px-3 py-3 font-mono text-sm break-all"
            aria-label="Temporary password"
          >
            {tempPassword ?? "—"}
          </div>
          {expiresAt && (
            <p className="text-xs text-muted-foreground">
              Expires at <time dateTime={expiresAt}>{new Date(expiresAt).toLocaleString()}</time>
            </p>
          )}
          <p className="text-xs text-destructive">
            Closing this dialog will discard the value. Make sure you have it.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={copy} disabled={!tempPassword}>
            <Copy className="mr-2 h-4 w-4" aria-hidden="true" /> Copy
          </Button>
          <Button
            variant="brand"
            onClick={() => {
              setConfirmed(true);
              onOpenChange(false);
            }}
          >
            I have copied it — Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
