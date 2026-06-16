"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type {
  BroadcastEstimate,
  BroadcastRequest,
  BroadcastResponse,
} from "@/types/admin";

export function useAdminBroadcastEstimate(req: BroadcastRequest | null) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "broadcast", "estimate", req],
    queryFn: () =>
      api.post<BroadcastEstimate>("/admin/broadcast/estimate", req as BroadcastRequest, { token }),
    enabled: !!token && !!req,
    staleTime: 10_000,
  });
}

export function useAdminSendBroadcast() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: ({ body, stepUpToken }: { body: BroadcastRequest; stepUpToken?: string }) =>
      api.post<BroadcastResponse>("/admin/broadcast", body, {
        token,
        headers: stepUpToken ? { "X-Step-Up-TOTP": stepUpToken } : undefined,
      }),
  });
}
