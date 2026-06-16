"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { NotificationPublic } from "@/types";

export function useNotifications(unreadOnly = false) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["notifications", { unreadOnly }],
    queryFn: async () => {
      const all = await api.get<NotificationPublic[]>("/notifications", { token });
      return unreadOnly ? all.filter((n) => !n.is_read) : all;
    },
    enabled: !!token,
    refetchInterval: 60_000,
  });
}

export function useMarkNotificationRead() {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ message: string }>(`/notifications/${id}/read`, undefined, { token }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
