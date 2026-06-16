"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import { useKillSwitchStore } from "@/store/kill-switch";
import type { StrategyInstancePublic } from "@/types";

/**
 * Per-instance emergency kill — calls POST /strategy-instances/{id}/kill.
 * We also flip a local Zustand store so the UI shows a banner everywhere.
 */
export function useKillInstance() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  const localTrigger = useKillSwitchStore((s) => s.trigger);
  return useMutation({
    mutationFn: ({ id }: { id: string; reason: string }) =>
      api.post<StrategyInstancePublic>(`/strategy-instances/${id}/kill`, undefined, {
        token,
      }),
    onSuccess: (_data, vars) => {
      localTrigger(vars.reason);
      qc.invalidateQueries({ queryKey: ["strategy-instances"] });
      qc.invalidateQueries({ queryKey: ["dashboard", "instances"] });
    },
  });
}

export function useResetKillSwitchUi() {
  const localReset = useKillSwitchStore((s) => s.reset);
  return localReset;
}
