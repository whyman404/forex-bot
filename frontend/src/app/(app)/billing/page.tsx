"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ExternalLink, FileText, Loader2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PricingCard } from "@/components/pricing-card";
import {
  useBillingMe,
  useBillingPlans,
  useCreateCheckout,
  useCreatePortal,
} from "@/hooks/use-billing";
import { ApiError } from "@/lib/api";
import { env, resolveBaseUrl } from "@/lib/env";
import { t } from "@/lib/i18n";
import type { Plan } from "@/types";

function formatCents(cents: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

/**
 * Billing page — Phase 2.
 * Drives the real Stripe Checkout + Customer Portal flow.
 * On return (`?session_id=…`) we poll /billing/me until status === "active".
 */
export default function BillingPage(): React.ReactElement {
  const params = useSearchParams();
  const sessionId = params.get("session_id");
  const canceled = params.get("canceled");

  const me = useBillingMe({
    // Aggressively poll for ~30s while we wait for Stripe webhook to mark the sub active.
    refetchIntervalMs: sessionId ? 2000 : undefined,
  });
  const plans = useBillingPlans();
  const checkout = useCreateCheckout();
  const portal = useCreatePortal();

  const [pollStartedAt] = React.useState<number>(() => (sessionId ? Date.now() : 0));
  const isActivating =
    !!sessionId &&
    me.data?.status !== "active" &&
    me.data?.status !== "trialing" &&
    Date.now() - pollStartedAt < 60_000;

  React.useEffect(() => {
    if (canceled) toast.message("Checkout canceled. No charge was made.");
  }, [canceled]);

  React.useEffect(() => {
    if (!sessionId) return;
    if (me.data?.status === "active" || me.data?.status === "trialing") {
      toast.success(t("billing.return.success"));
    }
  }, [sessionId, me.data?.status]);

  async function handleSubscribe(plan: Plan): Promise<void> {
    try {
      // Origin priority:
      //   1. NEXT_PUBLIC_BASE_URL — explicit canonical (production custom domain)
      //   2. window.location.origin — covers Vercel preview, localhost, ad-hoc
      // Stripe interpolates {CHECKOUT_SESSION_ID} on the success URL.
      const origin = env.NEXT_PUBLIC_BASE_URL ?? (typeof window !== "undefined" ? window.location.origin : resolveBaseUrl());
      const res = await checkout.mutateAsync({
        price_id: plan.price_id,
        success_url: `${origin}/billing?session_id={CHECKOUT_SESSION_ID}`,
        cancel_url: `${origin}/billing?canceled=1`,
      });
      if (typeof window !== "undefined") window.location.assign(res.url);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not start checkout",
      );
    }
  }

  async function handleManage(): Promise<void> {
    try {
      const res = await portal.mutateAsync();
      if (typeof window !== "undefined") window.location.assign(res.url);
    } catch (err) {
      toast.error(
        err instanceof ApiError ? err.message : "Could not open billing portal",
      );
    }
  }

  const currentPlanId: string | null =
    me.data?.plan === "pro" && me.data.cancel_at_period_end
      ? "pro_monthly"
      : me.data?.plan === "pro"
        ? "pro_monthly"
        : me.data?.plan === "enterprise"
          ? "lifetime"
          : me.data?.plan === "trial"
            ? "trial_14d"
            : null;

  const invoices = me.data?.invoices ?? [];

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">{t("billing.title")}</h1>
        <p className="text-sm text-muted-foreground">
          Manage your subscription and unlock live trading.
        </p>
      </header>

      {isActivating && (
        <Card className="border-warn/40 bg-warn/5">
          <CardContent className="flex items-center gap-3 py-4 text-sm">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>{t("billing.return.activating")}</span>
          </CardContent>
        </Card>
      )}

      {/* Current plan summary */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{t("billing.current_plan")}</CardTitle>
              <CardDescription>
                {me.data?.is_lifetime
                  ? "Lifetime — trade forever."
                  : me.data?.status === "active" || me.data?.status === "trialing"
                    ? "Live trading enabled."
                    : "Upgrade to enable live trading."}
              </CardDescription>
            </div>
            {me.isLoading ? (
              <Skeleton className="h-6 w-20" />
            ) : (
              <Badge variant={me.data?.status === "active" ? "profit" : "warn"}>
                {me.data?.plan ?? "free"} · {me.data?.status ?? "inactive"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1 text-sm">
            <p>
              <span className="text-muted-foreground">Renews:</span>{" "}
              <span className="font-medium">{formatDate(me.data?.current_period_end)}</span>
            </p>
            {me.data?.trial_ends_at ? (
              <p>
                <span className="text-muted-foreground">Trial ends:</span>{" "}
                <span className="font-medium">{formatDate(me.data.trial_ends_at)}</span>
              </p>
            ) : null}
          </div>
          {(me.data?.status === "active" || me.data?.status === "trialing") && !me.data?.is_lifetime ? (
            <Button variant="outline" onClick={handleManage} disabled={portal.isPending}>
              {portal.isPending ? "Opening…" : t("billing.manage")}
              <ExternalLink className="ml-2 h-4 w-4" aria-hidden="true" />
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {/* Plans */}
      <section aria-labelledby="plans-heading" className="space-y-3">
        <h2 id="plans-heading" className="text-lg font-semibold">
          Plans
        </h2>
        {plans.error && (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
          >
            {plans.error instanceof ApiError
              ? plans.error.message
              : "Could not load plans"}
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {plans.isLoading
            ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-72" />)
            : plans.data?.plans.map((p) => (
                <PricingCard
                  key={p.id}
                  plan={p}
                  currentPlanId={currentPlanId}
                  loading={checkout.isPending}
                  onSubscribe={handleSubscribe}
                />
              ))}
        </div>
      </section>

      {/* Invoices */}
      <section aria-labelledby="invoices-heading" className="space-y-3">
        <h2 id="invoices-heading" className="text-lg font-semibold">
          {t("billing.invoices")}
        </h2>
        <Card>
          <CardContent className="p-0">
            {me.isLoading ? (
              <div className="p-6">
                <Skeleton className="h-32" />
              </div>
            ) : invoices.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">No invoices yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Date</TableHead>
                    <TableHead>Invoice</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {invoices.map((inv) => (
                    <TableRow key={inv.id}>
                      <TableCell>{formatDate(inv.created_at)}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {inv.number ?? inv.id.slice(0, 8)}
                      </TableCell>
                      <TableCell>{formatCents(inv.amount_paid_cents, inv.currency)}</TableCell>
                      <TableCell>
                        <Badge variant={inv.status === "paid" ? "profit" : "warn"}>{inv.status}</Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {inv.hosted_invoice_url ? (
                          <Button asChild variant="ghost" size="sm">
                            <a
                              href={inv.hosted_invoice_url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <FileText className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
                              View
                            </a>
                          </Button>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>

      <p className="text-xs text-muted-foreground">
        All prices in USD. Tax may apply at checkout. By subscribing you agree to our terms and the
        risk disclosure.
      </p>
    </div>
  );
}
