"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { BacktestCreateRequest, BacktestPublic } from "@/types";

export function useBacktests(limit?: number) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["backtests", limit],
    queryFn: () =>
      api.get<BacktestPublic[]>("/backtests", { token, query: { limit } }),
    enabled: !!token,
  });
}

export function useBacktest(id: string | null) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["backtest", id],
    queryFn: () => api.get<BacktestPublic>(`/backtests/${id}`, { token }),
    enabled: !!token && !!id,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 2000;
      return data.status === "succeeded" ||
        data.status === "failed" ||
        data.status === "cancelled"
        ? false
        : 2000;
    },
  });
}

export function useCreateBacktest() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: BacktestCreateRequest) =>
      api.post<BacktestPublic>("/backtests", input, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backtests"] }),
  });
}

/**
 * Run a backtest and poll until it completes. Returns the in-progress backtest id
 * so callers can render skeletons while the polling query runs.
 */
export function useRunBacktest() {
  const create = useCreateBacktest();
  const [id, setId] = React.useState<string | null>(null);
  const polling = useBacktest(id);

  const reset = React.useCallback(() => setId(null), []);

  const run = React.useCallback(
    async (input: BacktestCreateRequest) => {
      const created = await create.mutateAsync(input);
      setId(created.id);
      return created;
    },
    [create],
  );

  return {
    run,
    reset,
    id,
    isQueueing: create.isPending,
    createError: create.error,
    backtest: polling.data ?? null,
    isPolling: polling.isFetching,
    pollError: polling.error,
  };
}
