"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type {
  AdminGrantSubscriptionRequest,
  AdminSubscription,
  Paginated,
} from "@/types/admin";
import type { SubscriptionPlan, SubscriptionStatus } from "@/types/domain";

export interface AdminSubscriptionQuery {
  plan?: SubscriptionPlan;
  status?: SubscriptionStatus;
  page?: number;
  per_page?: number;
}

export function useAdminSubscriptions(query: AdminSubscriptionQuery = {}) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "subscriptions", query],
    queryFn: () =>
      api.get<Paginated<AdminSubscription>>("/admin/subscriptions", {
        token,
        query: query as Record<string, string | number | boolean | undefined | null>,
      }),
    enabled: !!token,
    staleTime: 30_000,
  });
}

export function useAdminCancelSubscription() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post<AdminSubscription>(`/admin/subscriptions/${id}/cancel`, { reason }, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "subscriptions"] }),
  });
}

export function useAdminGrantSubscription() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminGrantSubscriptionRequest) =>
      api.post<AdminSubscription>("/admin/subscriptions/grant", body, { token }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "subscriptions"] });
      qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    },
  });
}
