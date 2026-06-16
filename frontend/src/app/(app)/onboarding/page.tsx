"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Mail,
  ShieldCheck,
  TrendingUp,
  WalletCards,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { OnboardingStepper } from "@/components/onboarding-stepper";
import { useOnboarding } from "@/hooks/use-onboarding";
import { useResendVerification } from "@/hooks/use-account";
import { useStrategies } from "@/hooks/use-strategies";
import { useCreateStrategyInstance } from "@/hooks/use-strategy-instance";
import { useBrokerAccounts } from "@/hooks/use-broker-accounts";
import { ApiError } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { OnboardingStep } from "@/types";

const STEPS = [
  { id: 1, label: "Verify email" },
  { id: 2, label: "Enable 2FA" },
  { id: 3, label: "Connect broker" },
  { id: 4, label: "Pick strategy" },
];

export default function OnboardingPage(): React.ReactElement {
  const router = useRouter();
  const onboarding = useOnboarding();
  const resend = useResendVerification();
  const strategies = useStrategies();
  const brokers = useBrokerAccounts();
  const create = useCreateStrategyInstance();

  const [selectedStrategy, setSelectedStrategy] = React.useState<string | null>(null);
  const { step, state, isLoading } = onboarding;

  React.useEffect(() => {
    // If user completed onboarding earlier, send them to the dashboard.
    if (!onboarding.isVisible && state.completed_at) {
      router.replace("/dashboard");
    }
  }, [onboarding.isVisible, state.completed_at, router]);

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  const completedSteps: number[] = [];
  if (state.email_verified) completedSteps.push(1);
  if (state.totp_enabled) completedSteps.push(2);
  if (state.broker_connected) completedSteps.push(3);
  if (state.paper_instance_created) completedSteps.push(4);

  function next(): void {
    const nextStep = Math.min(step + 1, 4) as OnboardingStep;
    onboarding.goTo(nextStep);
  }

  function back(): void {
    const prev = Math.max(step - 1, 1) as OnboardingStep;
    onboarding.goTo(prev);
  }

  async function handleResend(): Promise<void> {
    try {
      await resend.mutateAsync();
      toast.success("Verification email sent — check your inbox");
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        toast.message("Open the link in the email we sent at signup");
        return;
      }
      toast.error(err instanceof ApiError ? err.message : "Could not resend");
    }
  }

  async function handleCreatePaperInstance(): Promise<void> {
    if (!selectedStrategy) {
      toast.error("Pick a strategy first");
      return;
    }
    const placeholderBroker = brokers.data?.[0]?.id;
    try {
      await create.mutateAsync({
        strategy_code: selectedStrategy,
        broker_account_id: placeholderBroker ?? "00000000-0000-0000-0000-000000000000",
        label: `${selectedStrategy} — paper`,
        risk_config: { paper: true },
      });
      toast.success("Paper instance created");
      onboarding.complete();
      router.push("/dashboard");
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not create paper instance",
      );
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{t("onboarding.title")}</h1>
            <p className="text-sm text-muted-foreground">{t("onboarding.subtitle")}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => {
            onboarding.skip();
            router.push("/dashboard");
          }}>
            {t("onboarding.skip")}
          </Button>
        </div>
        <OnboardingStepper steps={STEPS} currentStep={step} completedSteps={completedSteps} />
      </header>

      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" aria-hidden="true" />
              {t("onboarding.step1.title")}
            </CardTitle>
            <CardDescription>{t("onboarding.step1.body")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {state.email_verified ? (
              <div className="flex items-center gap-2 rounded-md border border-profit/30 bg-profit/5 p-3 text-sm text-profit">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                {t("onboarding.step1.done")}
              </div>
            ) : (
              <Button variant="outline" onClick={handleResend} disabled={resend.isPending}>
                {resend.isPending ? "Sending…" : t("onboarding.step1.cta")}
              </Button>
            )}
            <StepFooter onBack={back} onNext={next} canGoNext={true} />
          </CardContent>
        </Card>
      )}

      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
              {t("onboarding.step2.title")}
            </CardTitle>
            <CardDescription>{t("onboarding.step2.body")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {state.totp_enabled ? (
              <div className="flex items-center gap-2 rounded-md border border-profit/30 bg-profit/5 p-3 text-sm text-profit">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                Two-factor authentication is enabled.
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm">
                  Open Settings → Security to scan the QR code with your authenticator app.
                </p>
                <Button asChild variant="outline">
                  <Link href="/settings">Open settings</Link>
                </Button>
              </div>
            )}
            <StepFooter onBack={back} onNext={next} canGoNext={true} />
          </CardContent>
        </Card>
      )}

      {step === 3 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <WalletCards className="h-5 w-5" aria-hidden="true" />
              {t("onboarding.step3.title")}
            </CardTitle>
            <CardDescription>{t("onboarding.step3.body")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {state.broker_connected ? (
              <div className="flex items-center gap-2 rounded-md border border-profit/30 bg-profit/5 p-3 text-sm text-profit">
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                Broker connected.
              </div>
            ) : (
              <div className="space-y-3">
                <Button asChild variant="outline">
                  <Link href="/broker">Connect broker</Link>
                </Button>
                <Button variant="ghost" size="sm" onClick={next}>
                  {t("onboarding.step3.skip")}
                </Button>
              </div>
            )}
            <StepFooter onBack={back} onNext={next} canGoNext={true} />
          </CardContent>
        </Card>
      )}

      {step === 4 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" aria-hidden="true" />
              {t("onboarding.step4.title")}
            </CardTitle>
            <CardDescription>{t("onboarding.step4.body")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {strategies.isLoading ? (
              <Skeleton className="h-32" />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {strategies.data?.map((s) => {
                  const isSelected = selectedStrategy === s.code;
                  return (
                    <button
                      key={s.code}
                      type="button"
                      onClick={() => setSelectedStrategy(s.code)}
                      className={`flex flex-col items-start gap-1 rounded-md border p-3 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        isSelected
                          ? "border-brand bg-brand/5"
                          : "border-input hover:border-brand/40"
                      }`}
                      aria-pressed={isSelected}
                    >
                      <div className="flex w-full items-center justify-between">
                        <span className="font-semibold">{s.name}</span>
                        {isSelected && <Badge variant="profit">Selected</Badge>}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {s.asset} · {s.timeframe}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Button variant="ghost" onClick={back}>
                <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
                {t("common.back")}
              </Button>
              <Button
                variant="brand"
                onClick={handleCreatePaperInstance}
                disabled={!selectedStrategy || create.isPending}
              >
                {create.isPending ? "Creating…" : t("onboarding.complete")}
                <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function StepFooter({
  onBack,
  onNext,
  canGoNext,
}: {
  onBack: () => void;
  onNext: () => void;
  canGoNext: boolean;
}): React.ReactElement {
  return (
    <div className="flex items-center justify-between gap-3 border-t pt-3">
      <Button variant="ghost" onClick={onBack}>
        <ArrowLeft className="mr-2 h-4 w-4" aria-hidden="true" />
        {t("common.back")}
      </Button>
      <Button variant="brand" onClick={onNext} disabled={!canGoNext}>
        {t("common.continue")}
        <ArrowRight className="ml-2 h-4 w-4" aria-hidden="true" />
      </Button>
    </div>
  );
}
