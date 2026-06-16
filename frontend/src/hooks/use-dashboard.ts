"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type {
  BacktestPublic,
  NotificationPublic,
  StrategyInstancePublic,
} from "@/types";

/**
 * Aggregated dashboard data — fetched in parallel by react-query.
 * Each piece is its own hook so a single failure doesn't blank the page.
 */
export function useDashboardInstances() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["dashboard", "instances"],
    queryFn: () =>
      api.get<StrategyInstancePublic[]>("/strategy-instances", { token }),
    enabled: !!token,
    refetchInterval: 30_000,
  });
}

export function useDashboardBacktests(limit = 5) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["dashboard", "backtests", limit],
    queryFn: () =>
      api.get<BacktestPublic[]>("/backtests", { token, query: { limit } }),
    enabled: !!token,
    refetchInterval: 30_000,
  });
}

export function useDashboardUnreadNotifications() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["dashboard", "notifications", "unread"],
    queryFn: async () => {
      const all = await api.get<NotificationPublic[]>("/notifications", { token });
      return all.filter((n) => !n.is_read);
    },
    enabled: !!token,
    refetchInterval: 60_000,
  });
}
