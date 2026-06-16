"use client";

import * as React from "react";
import { toast } from "sonner";
import { AlertTriangle, CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";
import { GateCheckList } from "@/components/gate-check-list";
import {
  useGoLive,
  useLiveEligibility,
  useSignLiveConsent,
} from "@/hooks/use-live-trading";
import { useTVHealthOk } from "@/hooks/use-tradingview";
import { ApiError } from "@/lib/api";

const REQUIRED_PHRASE = "GO LIVE";

interface LiveTradingModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instanceId: string;
  instanceLabel: string;
  /**
   * Strategy code of the instance. When set to "tv_signal", an extra gate is
   * enforced: TradingView health must report `ok` before the user can submit.
   * The check polls every 30s via useTVHealth.
   */
  strategyCode?: string | null;
  onSuccess?: () => void;
}

/**
 * The safety gate for switching a paper instance to live.
 * Multiple intentional friction points:
 *   1. Modal cannot be confirmed via Enter without typing the exact phrase.
 *   2. Confirm button is disabled until BOTH eligibility passes AND phrase matches.
 *   3. User must explicitly check the risk-acknowledgement box.
 *   4. The "GO LIVE" phrase is case-sensitive and trimmed.
 *   5. Submitting calls `/live-consents` first, then `/go-live` so consent is
 *      auditable even if the live action fails.
 */
export function LiveTradingModal({
  open,
  onOpenChange,
  instanceId,
  instanceLabel,
  strategyCode,
  onSuccess,
}: LiveTradingModalProps): React.ReactElement {
  const eligibility = useLiveEligibility(open ? instanceId : null);
  const signConsent = useSignLiveConsent();
  const goLive = useGoLive(instanceId);

  const isTVSignal = strategyCode === "tv_signal";
  const tvHealth = useTVHealthOk();

  const [phrase, setPhrase] = React.useState("");
  const [accepted, setAccepted] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setPhrase("");
      setAccepted(false);
      setSubmitting(false);
    }
  }, [open]);

  const allGatesPassed = eligibility.data?.eligible ?? false;
  const passed = eligibility.data?.gates.filter((g) => g.passed).length ?? 0;
  const total = eligibility.data?.gates.length ?? 0;
  const phraseMatches = phrase.trim() === REQUIRED_PHRASE;
  const consentVersion = eligibility.data?.required_consent_version ?? "1.1.0";

  // tv_signal: TradingView health must be OK before going live.
  const tvGatePasses = !isTVSignal || tvHealth.ok;

  const canSubmit =
    allGatesPassed && phraseMatches && accepted && tvGatePasses && !submitting;

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const consent = await signConsent.mutateAsync({
        version: consentVersion,
        acknowledgement: phrase,
      });
      await goLive.mutateAsync({
        confirmation_phrase: REQUIRED_PHRASE,
        consent_id: consent.id,
      });
      toast.success("Live trading enabled. Monitor the dashboard.");
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not enable live trading",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <ShieldAlert className="h-5 w-5" aria-hidden="true" />
            Enable live trading — real money
          </DialogTitle>
          <DialogDescription>
            You are about to switch <strong>{instanceLabel}</strong> from paper to live.
            Losses can exceed your deposit. Complete every safety check below.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {/* Eligibility */}
          <section aria-labelledby="gates-heading" className="space-y-2">
            <h3 id="gates-heading" className="text-sm font-semibold">
              Safety gates ({passed} / {total} passed)
            </h3>
            {eligibility.isLoading ? (
              <GateCheckList gates={[]} loading />
            ) : eligibility.error ? (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                Could not load eligibility — try again.
              </p>
            ) : (
              <GateCheckList gates={eligibility.data?.gates ?? []} />
            )}
          </section>

          {/* Extra TV gate for tv_signal instances */}
          {isTVSignal && (
            <section
              aria-labelledby="tv-gate-heading"
              className={[
                "rounded-md border p-3 text-sm",
                tvGatePasses
                  ? "border-profit/40 bg-profit/5"
                  : "border-destructive/40 bg-destructive/5",
              ].join(" ")}
            >
              <h3 id="tv-gate-heading" className="flex items-center gap-2 text-sm font-semibold">
                {tvGatePasses ? (
                  <CheckCircle2 className="h-4 w-4 text-profit" aria-hidden="true" />
                ) : (
                  <XCircle className="h-4 w-4 text-destructive" aria-hidden="true" />
                )}
                TradingView health
              </h3>
              <p className="mt-1 text-xs text-muted-foreground" aria-live="polite">
                {tvHealth.loading
                  ? "Checking TradingView integration…"
                  : tvGatePasses
                    ? "TradingView is responding normally. Signals can be routed to your broker."
                    : (tvHealth.reason ??
                      "TradingView health check failed. You cannot go live with tv_signal until this clears.")}
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Auto-polled every 30 seconds. Required for tv_signal instances only.
              </p>
            </section>
          )}

          {/* Risk acknowledgement */}
          <div className="space-y-2 rounded-md border border-warn/40 bg-warn/5 p-3 text-sm">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
              <p>
                I understand that <strong>past performance is not indicative of future results</strong>.
                Leveraged FX/crypto trading carries substantial risk. I will only trade with funds I can afford to lose.
              </p>
            </div>
            <label className="flex cursor-pointer items-center gap-2 pt-1">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
                className="h-4 w-4 rounded border-input"
                aria-describedby="risk-note"
                required
              />
              <span id="risk-note" className="text-sm font-medium">
                I accept the risk disclosure (v{consentVersion})
              </span>
            </label>
          </div>

          {/* Typed confirmation */}
          <div className="space-y-1.5">
            <Label htmlFor="live-phrase">
              Type <code className="rounded bg-muted px-1 py-0.5 text-xs">GO LIVE</code> to enable
            </Label>
            <Input
              id="live-phrase"
              value={phrase}
              onChange={(e) => setPhrase(e.target.value)}
              placeholder="GO LIVE"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              aria-invalid={phrase.length > 0 && !phraseMatches}
              aria-describedby="live-phrase-help"
              disabled={!allGatesPassed}
            />
            <p id="live-phrase-help" className="text-xs text-muted-foreground">
              Case-sensitive. Whitespace is trimmed.
            </p>
          </div>

          <DialogFooter className="gap-2 sm:gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!canSubmit}
              aria-disabled={!canSubmit}
            >
              {submitting ? "Enabling…" : "Enable live trading"}
            </Button>
          </DialogFooter>

          {!allGatesPassed && eligibility.data ? (
            <p className="text-xs text-muted-foreground">
              Resolve the failing checks above before you can enable live trading.
            </p>
          ) : null}
          {allGatesPassed && isTVSignal && !tvGatePasses ? (
            <p className="text-xs text-destructive">
              TradingView integration must be healthy before this strategy can go live.
            </p>
          ) : null}
        </form>
      </DialogContent>
    </Dialog>
  );
}

interface RevertToPaperModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  instanceLabel: string;
  onConfirm: (reason: string) => Promise<void>;
}

export function RevertToPaperModal({
  open,
  onOpenChange,
  instanceLabel,
  onConfirm,
}: RevertToPaperModalProps): React.ReactElement {
  const [reason, setReason] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setReason("");
      setSubmitting(false);
    }
  }, [open]);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setSubmitting(true);
    try {
      await onConfirm(reason);
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not revert to paper");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revert {instanceLabel} to paper</DialogTitle>
          <DialogDescription>
            Open live positions stay open at the broker — the bot will stop placing new live
            orders and resume in paper mode.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="revert-reason">Reason (optional)</Label>
            <Input
              id="revert-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Drawdown too high"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="brand" disabled={submitting}>
              {submitting ? "Reverting…" : "Revert to paper"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
