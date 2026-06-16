"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { TotpEnrollResponse } from "@/types";

export function useTotpEnroll() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: () =>
      api.post<TotpEnrollResponse>("/auth/totp/enroll", undefined, { token }),
  });
}

export function useTotpVerify() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (code: string) =>
      api.post<{ message: string }>("/auth/totp/verify", { code }, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}
