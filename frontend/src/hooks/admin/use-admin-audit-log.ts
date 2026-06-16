"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "@/hooks/use-session-token";
import type {
  AdminAuditLogEntry,
  AdminAuditLogQuery,
  Paginated,
} from "@/types/admin";

export function useAdminAuditLog(query: AdminAuditLogQuery = {}) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["admin", "audit-log", query],
    queryFn: () =>
      api.get<Paginated<AdminAuditLogEntry>>("/admin/audit-log", {
        token,
        query: query as Record<string, string | number | boolean | undefined | null>,
      }),
    enabled: !!token,
    staleTime: 10_000,
  });
}

/**
 * Returns absolute URL to the CSV export endpoint.
 * The endpoint must accept Bearer auth and stream CSV.
 */
export function adminAuditLogCsvUrl(query: AdminAuditLogQuery = {}): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null) continue;
    params.append(k, String(v));
  }
  const q = params.toString();
  return `/admin/audit-log/export.csv${q ? `?${q}` : ""}`;
}
