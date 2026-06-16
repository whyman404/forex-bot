"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type {
  BrokerAccountCreateRequest,
  BrokerAccountPublic,
  BrokerConnectionTestResponse,
} from "@/types";

export function useBrokerAccounts() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["broker-accounts"],
    queryFn: () => api.get<BrokerAccountPublic[]>("/broker-accounts", { token }),
    enabled: !!token,
  });
}

export function useCreateBrokerAccount() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: BrokerAccountCreateRequest) =>
      api.post<BrokerAccountPublic>("/broker-accounts", input, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["broker-accounts"] }),
  });
}

export function useDeleteBrokerAccount() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.delete<void>(`/broker-accounts/${id}`, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["broker-accounts"] }),
  });
}

export function useTestBrokerConnection() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<BrokerConnectionTestResponse>(
        `/broker-accounts/${id}/test-connection`,
        undefined,
        { token },
      ),
  });
}
