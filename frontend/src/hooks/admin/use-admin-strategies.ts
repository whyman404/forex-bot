"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type { AdminStrategy, AdminStrategyUpdateRequest } from "@/types/admin";

export function useAdminStrategies() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "strategies"],
    queryFn: () => api.get<AdminStrategy[]>("/admin/strategies", { token }),
    enabled: !!token,
    staleTime: 15_000,
  });
}

export function useAdminUpdateStrategy() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminStrategyUpdateRequest }) =>
      api.patch<AdminStrategy>(`/admin/strategies/${id}`, body, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "strategies"] }),
  });
}

export function useAdminKillAllStrategyInstances() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      reason,
      stepUpToken,
    }: {
      id: string;
      reason: string;
      stepUpToken: string;
    }) =>
      api.post<{ killed: number }>(
        `/admin/strategies/${id}/kill-all`,
        { reason },
        { token, headers: { "X-Step-Up-TOTP": stepUpToken } },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "strategies"] }),
  });
}
