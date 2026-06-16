"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { Strategy, StrategyPublic } from "@/types";
import { toStrategy } from "@/types";

export function useStrategies() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["strategies"],
    queryFn: async (): Promise<Strategy[]> => {
      const raw = await api.get<StrategyPublic[]>("/strategies", { token });
      return raw.map(toStrategy);
    },
    enabled: !!token,
    staleTime: 5 * 60_000,
  });
}

export function useStrategy(code: string) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["strategy", code],
    queryFn: async (): Promise<Strategy> => {
      const raw = await api.get<StrategyPublic>(`/strategies/${code}`, { token });
      return toStrategy(raw);
    },
    enabled: !!token && !!code,
    staleTime: 5 * 60_000,
  });
}
