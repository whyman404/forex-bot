"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type {
  AdminBulkBanRequest,
  AdminImpersonateResponse,
  AdminResetPasswordResponse,
  AdminUserBacktest,
  AdminUserBrokerAccount,
  AdminUserConsent,
  AdminUserDetail,
  AdminUserInstance,
  AdminUserListItem,
  AdminUserListQuery,
  AdminUserUpdateRequest,
  Paginated,
} from "@/types/admin";

/**
 * Admin user-management hooks. All endpoints are namespaced `/admin/*` and
 * require `role === "admin"` server-side. The middleware also gates `/admin`
 * routes client-side.
 *
 * Step-up token: destructive actions (reset_password, impersonate, ban, delete)
 * accept an optional `stepUpToken` that is forwarded as `X-Step-Up-TOTP`.
 */

function stepUpHeaders(token?: string | null): Record<string, string> {
  return token ? { "X-Step-Up-TOTP": token } : {};
}

export function useAdminUsers(query: AdminUserListQuery = {}) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", query],
    queryFn: () =>
      api.get<Paginated<AdminUserListItem>>("/admin/users", {
        token,
        query: query as Record<string, string | number | boolean | undefined | null>,
      }),
    enabled: !!token,
    staleTime: 15_000,
  });
}

export function useAdminUser(id: string | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", id],
    queryFn: () => api.get<AdminUserDetail>(`/admin/users/${id}`, { token }),
    enabled: !!token && !!id,
    staleTime: 5_000,
  });
}

export function useAdminUserBrokerAccounts(id: string | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", id, "brokers"],
    queryFn: () =>
      api.get<AdminUserBrokerAccount[]>(`/admin/users/${id}/broker-accounts`, { token }),
    enabled: !!token && !!id,
  });
}

export function useAdminUserInstances(id: string | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", id, "instances"],
    queryFn: () => api.get<AdminUserInstance[]>(`/admin/users/${id}/instances`, { token }),
    enabled: !!token && !!id,
  });
}

export function useAdminUserBacktests(id: string | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", id, "backtests"],
    queryFn: () =>
      api.get<AdminUserBacktest[]>(`/admin/users/${id}/backtests`, {
        token,
        query: { limit: 10 },
      }),
    enabled: !!token && !!id,
  });
}

export function useAdminUserConsents(id: string | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "users", id, "consents"],
    queryFn: () => api.get<AdminUserConsent[]>(`/admin/users/${id}/consents`, { token }),
    enabled: !!token && !!id,
  });
}

export function useAdminUpdateUser() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AdminUserUpdateRequest }) =>
      api.patch<AdminUserDetail>(`/admin/users/${id}`, body, { token }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["admin", "users", vars.id] });
      qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    },
  });
}

export function useAdminResetPassword() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: ({ id, stepUpToken }: { id: string; stepUpToken?: string }) =>
      api.post<AdminResetPasswordResponse>(`/admin/users/${id}/reset-password`, undefined, {
        token,
        headers: stepUpHeaders(stepUpToken),
      }),
  });
}

export function useAdminImpersonate() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: ({
      id,
      stepUpToken,
      reason,
    }: {
      id: string;
      stepUpToken: string;
      reason: string;
    }) =>
      api.post<AdminImpersonateResponse>(
        `/admin/users/${id}/impersonate`,
        { reason },
        {
          token,
          headers: stepUpHeaders(stepUpToken),
        },
      ),
  });
}

export function useAdminBanUser() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      reason,
      stepUpToken,
    }: {
      id: string;
      reason: string;
      stepUpToken?: string;
    }) =>
      api.post<AdminUserDetail>(
        `/admin/users/${id}/ban`,
        { reason },
        { token, headers: stepUpHeaders(stepUpToken) },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["admin", "users", vars.id] });
      qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    },
  });
}

export function useAdminUnbanUser() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.post<AdminUserDetail>(`/admin/users/${id}/unban`, undefined, { token }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ["admin", "users", vars.id] });
      qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    },
  });
}

export function useAdminDeleteUser() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      confirmation_phrase,
      stepUpToken,
    }: {
      id: string;
      confirmation_phrase: string;
      stepUpToken?: string;
    }) =>
      api.delete<void>(`/admin/users/${id}`, {
        token,
        headers: stepUpHeaders(stepUpToken),
        body: { confirmation_phrase },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false });
    },
  });
}

export function useAdminBulkBan() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      body,
      stepUpToken,
    }: {
      body: AdminBulkBanRequest;
      stepUpToken?: string;
    }) =>
      api.post<{ banned: number }>("/admin/users/bulk-ban", body, {
        token,
        headers: stepUpHeaders(stepUpToken),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"], exact: false }),
  });
}
