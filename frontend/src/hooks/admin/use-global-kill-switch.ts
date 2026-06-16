"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type {
  GlobalKillDisarmRequest,
  GlobalKillRequest,
  GlobalKillStatus,
} from "@/types/admin";

export function useGlobalKillStatus() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "global-kill"],
    queryFn: () => api.get<GlobalKillStatus>("/admin/system/global-kill", { token }),
    enabled: !!token,
    refetchInterval: 15_000,
    staleTime: 5_000,
  });
}

export function useEngageGlobalKill() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ body, stepUpToken }: { body: GlobalKillRequest; stepUpToken: string }) =>
      api.post<GlobalKillStatus>("/admin/system/global-kill/engage", body, {
        token,
        headers: { "X-Step-Up-TOTP": stepUpToken },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "global-kill"] }),
  });
}

export function useDisarmGlobalKill() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      body,
      stepUpToken,
    }: {
      body: GlobalKillDisarmRequest;
      stepUpToken: string;
    }) =>
      api.post<GlobalKillStatus>("/admin/system/global-kill/disarm", body, {
        token,
        headers: { "X-Step-Up-TOTP": stepUpToken },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "global-kill"] }),
  });
}
