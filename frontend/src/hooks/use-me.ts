"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { UserPublic } from "@/types";

export function useMe() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<UserPublic>("/users/me", { token }),
    enabled: !!token,
    staleTime: 60_000,
  });
}
