"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type { AdminDependencyHealthResponse } from "@/types/admin";

/**
 * Dependency health for the System dashboard — pings postgres, redis, stripe,
 * email, mt5-bridge, tradingview. Refetch every 30s.
 */
export function useAdminDepHealth() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "dep-health"],
    queryFn: () => api.get<AdminDependencyHealthResponse>("/admin/system/dependencies", { token }),
    enabled: !!token,
    refetchInterval: 30_000,
    staleTime: 15_000,
    // Do NOT retry health probes — failures ARE the signal.
    retry: false,
  });
}
