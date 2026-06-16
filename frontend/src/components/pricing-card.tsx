"use client";

import * as React from "react";
import { CheckCircle2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Plan } from "@/types";

interface PricingCardProps {
  plan: Plan;
  /** ID of the user's current plan. Used to show a "Current plan" badge. */
  currentPlanId?: string | null;
  loading?: boolean;
  onSubscribe: (plan: Plan) => void;
}

function formatPrice(amountCents: number, currency: string, interval: Plan["interval"]): string {
  if (amountCents === 0) return "Free";
  const amount = amountCents / 100;
  const formatted = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency.toUpperCase(),
    maximumFractionDigits: 0,
  }).format(amount);
  switch (interval) {
    case "month":
      return `${formatted} / mo`;
    case "year":
      return `${formatted} / yr`;
    case "lifetime":
      return `${formatted} once`;
    default:
      return formatted;
  }
}

export function PricingCard({ plan, currentPlanId, loading, onSubscribe }: PricingCardProps): React.ReactElement {
  const isCurrent = currentPlanId === plan.id;
  const isHighlighted = plan.highlight ?? false;

  return (
    <Card
      aria-label={`${plan.name} plan`}
      className={cn(
        "relative flex flex-col",
        isHighlighted && "border-brand shadow-lg",
        isCurrent && "ring-2 ring-brand/60",
      )}
    >
      {isHighlighted && (
        <Badge variant="warn" className="absolute -top-3 right-4">
          <Sparkles className="mr-1 h-3 w-3" aria-hidden="true" />
          Most popular
        </Badge>
      )}
      {plan.savings_label && !isHighlighted && (
        <Badge variant="profit" className="absolute -top-3 right-4">
          {plan.savings_label}
        </Badge>
      )}
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>{plan.name}</CardTitle>
          {isCurrent && <Badge variant="profit">Current plan</Badge>}
        </div>
        <CardDescription>{plan.description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <div className="text-3xl font-bold tracking-tight">
          {formatPrice(plan.amount_cents, plan.currency, plan.interval)}
        </div>
        {plan.trial_days ? (
          <p className="mt-1 text-xs text-muted-foreground">No credit card required</p>
        ) : null}
        <ul className="mt-5 flex-1 space-y-2 text-sm">
          {plan.features.map((f) => (
            <li key={f} className="flex items-start gap-2">
              <CheckCircle2
                className="mt-0.5 h-4 w-4 shrink-0 text-profit"
                aria-hidden="true"
              />
              <span>{f}</span>
            </li>
          ))}
        </ul>
        <Button
          variant={isHighlighted ? "brand" : "outline"}
          className="mt-6 w-full"
          disabled={loading || isCurrent}
          onClick={() => onSubscribe(plan)}
        >
          {isCurrent ? "Current plan" : loading ? "Opening…" : plan.amount_cents === 0 ? "Start trial" : "Subscribe"}
        </Button>
      </CardContent>
    </Card>
  );
}
