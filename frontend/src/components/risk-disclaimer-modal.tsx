"use client";

import * as React from "react";
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
import { useSignLiveConsent } from "@/hooks/use-live-trading";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";

const STORAGE_KEY = "forex-bot.risk-disclaimer.version";
const CURRENT_VERSION = "1.0.0";

interface RiskDisclaimerModalProps {
  /** When true the modal will auto-open if the user has not yet accepted this version. */
  triggerOnMount?: boolean;
  /** External control for non-auto cases. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function RiskDisclaimerModal({
  triggerOnMount = false,
  open: controlledOpen,
  onOpenChange,
}: RiskDisclaimerModalProps): React.ReactElement | null {
  const [internalOpen, setInternalOpen] = React.useState(false);
  const [accepted, setAccepted] = React.useState(false);
  const sign = useSignLiveConsent();

  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  React.useEffect(() => {
    if (!triggerOnMount) return;
    if (typeof window === "undefined") return;
    const seenVersion = window.localStorage.getItem(STORAGE_KEY);
    if (seenVersion !== CURRENT_VERSION) {
      setInternalOpen(true);
    }
  }, [triggerOnMount]);

  async function handleAccept(): Promise<void> {
    try {
      await sign.mutateAsync({
        version: CURRENT_VERSION,
        acknowledgement: "ACCEPTED",
      });
    } catch (err) {
      // We still gate the UI by localStorage so accidental signin doesn't block users.
      if (!(err instanceof ApiError) || err.status !== 404) {
        toast.error("Could not record consent — please try again");
        return;
      }
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, CURRENT_VERSION);
    }
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("risk.disclaimer.title")}</DialogTitle>
          <DialogDescription>Required before any live trading action.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <p>{t("risk.disclaimer.body")}</p>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            <li>Forex and crypto are leveraged products — losses can exceed deposit.</li>
            <li>Backtest results do not guarantee live performance.</li>
            <li>You are responsible for the parameters you choose.</li>
            <li>We may pause your strategies during exchange outages or risk events.</li>
          </ul>
          <label className="flex cursor-pointer items-center gap-2 rounded-md border p-2">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(e) => setAccepted(e.target.checked)}
              className="h-4 w-4"
            />
            <span className="text-sm font-medium">{t("risk.disclaimer.acknowledge")}</span>
          </label>
          <p className="text-xs text-muted-foreground">Consent version: v{CURRENT_VERSION}</p>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="brand"
            disabled={!accepted || sign.isPending}
            onClick={handleAccept}
          >
            {sign.isPending ? "Saving…" : "I accept"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
