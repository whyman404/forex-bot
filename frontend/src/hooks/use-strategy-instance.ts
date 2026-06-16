"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type {
  StrategyInstanceCreateRequest,
  StrategyInstancePublic,
} from "@/types";

export function useStrategyInstances() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["strategy-instances"],
    queryFn: () =>
      api.get<StrategyInstancePublic[]>("/strategy-instances", { token }),
    enabled: !!token,
    refetchInterval: 15_000,
  });
}

export function useCreateStrategyInstance() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: StrategyInstanceCreateRequest) =>
      api.post<StrategyInstancePublic>("/strategy-instances", input, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategy-instances"] }),
  });
}

type InstanceAction = "start" | "stop" | "kill";

export function useStrategyInstanceAction() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: InstanceAction }) =>
      api.post<StrategyInstancePublic>(`/strategy-instances/${id}/${action}`, undefined, {
        token,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategy-instances"] }),
  });
}
