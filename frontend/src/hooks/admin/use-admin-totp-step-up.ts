"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type { TotpStepUpResponse } from "@/types/admin";

/**
 * Step-up authentication: admin re-enters their TOTP code to receive a
 * short-lived token (~5 min) attached as `X-Step-Up-TOTP` to destructive
 * actions (impersonate, ban, delete user, kill-all, global kill, broadcast).
 *
 * Argus R4 coordinates the backend logic — frontend just renders the modal,
 * captures the code, and routes the token.
 */
export function useAdminStepUp() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: (totp_code: string) =>
      api.post<TotpStepUpResponse>("/admin/auth/step-up", { totp_code }, { token }),
  });
}
