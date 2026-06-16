"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type { AdminSystemMetrics } from "@/types/admin";

/**
 * System KPI dashboard — refetch every 30s so the operator sees fresh data
 * without manually reloading. Background refetch is gated to `document.visible`
 * by TanStack defaults so we don't burn bandwidth in a hidden tab.
 */
export function useAdminMetrics() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "metrics"],
    queryFn: () => api.get<AdminSystemMetrics>("/admin/system/metrics", { token }),
    enabled: !!token,
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
