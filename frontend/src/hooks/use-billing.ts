"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type {
  CheckoutSessionRequest,
  CheckoutSessionResponse,
  CustomerPortalResponse,
  PlansResponse,
  SubscriptionPublic,
} from "@/types";

const FALLBACK_PLANS: PlansResponse = {
  plans: [
    {
      id: "trial_14d",
      price_id: "trial",
      name: "Free Trial",
      description: "14 days. Paper trading only.",
      amount_cents: 0,
      currency: "usd",
      interval: "trial",
      trial_days: 14,
      features: [
        "All 6 strategies",
        "Unlimited backtests",
        "Paper trading on demo broker",
        "Email support",
      ],
    },
    {
      id: "pro_monthly",
      price_id: "price_pro_monthly",
      name: "Pro Monthly",
      description: "Live trading, billed monthly.",
      amount_cents: 2900,
      currency: "usd",
      interval: "month",
      features: [
        "Everything in Trial",
        "Live trading (1 broker)",
        "Real-time signal alerts",
        "Priority support",
      ],
      highlight: true,
    },
    {
      id: "pro_yearly",
      price_id: "price_pro_yearly",
      name: "Pro Yearly",
      description: "Save 17% billed annually.",
      amount_cents: 29000,
      currency: "usd",
      interval: "year",
      features: [
        "Everything in Pro Monthly",
        "Save 17% vs monthly",
        "Up to 2 broker accounts",
      ],
      savings_label: "Save 17%",
    },
    {
      id: "lifetime",
      price_id: "price_lifetime",
      name: "Lifetime",
      description: "Pay once, trade forever.",
      amount_cents: 99000,
      currency: "usd",
      interval: "lifetime",
      is_lifetime: true,
      features: [
        "Everything in Pro Yearly",
        "Up to 5 broker accounts",
        "1:1 onboarding session",
        "Lifetime updates",
      ],
    },
  ],
};

/** GET /billing/plans — falls back to in-memory catalog if the API is not deployed yet. */
export function useBillingPlans() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["billing", "plans"],
    queryFn: async () => {
      try {
        return await api.get<PlansResponse>("/billing/plans", { token });
      } catch {
        // Pre-launch fallback — keep the page rendering while Atlas wires the route.
        return FALLBACK_PLANS;
      }
    },
    enabled: !!token,
    staleTime: 5 * 60_000,
  });
}

/** GET /billing/me — current subscription + invoice list. */
export function useBillingMe(options?: { refetchIntervalMs?: number }) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["billing", "me"],
    queryFn: () => api.get<SubscriptionPublic>("/billing/me", { token }),
    enabled: !!token,
    refetchInterval: options?.refetchIntervalMs,
    retry: 1,
  });
}

/** POST /billing/checkout-session — returns the Stripe-hosted URL to redirect to. */
export function useCreateCheckout() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: (input: CheckoutSessionRequest) =>
      api.post<CheckoutSessionResponse, CheckoutSessionRequest>(
        "/billing/checkout-session",
        input,
        { token },
      ),
  });
}

/** POST /billing/customer-portal — returns the Stripe portal URL. */
export function useCreatePortal() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: () =>
      api.post<CustomerPortalResponse>(
        "/billing/customer-portal",
        undefined,
        { token },
      ),
  });
}

/** Helper for polling activation after returning from Checkout. */
export function useActivationPoll(enabled: boolean) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["billing", "me", "polling"],
    queryFn: async () => {
      const me = qc.getQueryData<SubscriptionPublic>(["billing", "me"]);
      return me ?? null;
    },
    enabled,
    refetchInterval: 2000,
  });
}
