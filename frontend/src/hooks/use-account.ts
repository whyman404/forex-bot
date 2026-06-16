"use client";

import { useMutation } from "@tanstack/react-query";
import { signOut } from "next-auth/react";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { DataExportResponse, DeleteAccountRequest } from "@/types";

/** POST /users/me/export — schedules a GDPR export, email contains the download link. */
export function useExportMyData() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: () =>
      api.post<DataExportResponse>("/users/me/export", undefined, { token }),
  });
}

/** DELETE /users/me — schedules account deletion (30-day grace period). */
export function useDeleteAccount() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: async (input: DeleteAccountRequest) => {
      // Backend `delete /users/me` is the canonical route; the typed confirmation
      // is captured client-side and signed via a request header for audit.
      await api.delete<void>("/users/me", {
        token,
        headers: { "X-Delete-Confirmation": input.confirmation_phrase },
      });
    },
    onSuccess: () => signOut({ callbackUrl: "/" }),
  });
}

/** POST /auth/resend-verification — resend the email-confirm link. */
export function useResendVerification() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/auth/resend-verification", undefined, { token }),
  });
}
