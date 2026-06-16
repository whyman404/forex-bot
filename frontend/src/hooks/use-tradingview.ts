"use client";

/**
 * TradingView Signal hooks — Round 5.
 *
 * Backend contract:
 *  - GET  /tv/symbols   → TVSymbol[]
 *  - POST /tv/preview   → TVPreview (multi-TF analysis snapshot)
 *  - GET  /tv/health    → { status: "ok" | "degraded" | "down", ... }
 *
 * Refetch cadence intentionally conservative:
 *  - symbols  → 1h (catalog rarely changes)
 *  - preview  → 60s when caller is on the strategy detail page
 *  - health   → 30s (live-trading gate consumes it)
 *
 * UI gracefully degrades when backend returns 503 (TV_ENABLED=false).
 */

import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type { TVHealth, TVPreview, TVPreviewRequest, TVSymbol } from "@/types";

const HOUR_MS = 60 * 60_000;

export function useTVSymbols() {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["tv", "symbols"],
    queryFn: () => api.get<TVSymbol[]>("/tv/symbols", { token }),
    enabled: !!token,
    staleTime: HOUR_MS,
    // 503 = TV disabled on backend; do not hammer.
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 503) return false;
      return failureCount < 2;
    },
  });
}

export interface UseTVPreviewArgs {
  symbol: string | null;
  intervals: readonly string[];
  /** Pass false on screens where polling is wasteful (e.g. backtest tab). */
  enabled?: boolean;
}

export function useTVPreview({ symbol, intervals, enabled = true }: UseTVPreviewArgs) {
  const { token } = useSessionToken();
  const intervalsKey = [...intervals].sort().join(",");
  const isReady = !!token && !!symbol && intervals.length > 0 && enabled;
  return useQuery({
    queryKey: ["tv", "preview", symbol, intervalsKey],
    queryFn: () => {
      const body: TVPreviewRequest = {
        symbol: symbol as string,
        intervals: [...intervals],
      };
      return api.post<TVPreview, TVPreviewRequest>("/tv/preview", body, { token });
    },
    enabled: isReady,
    refetchInterval: isReady ? 60_000 : false,
    refetchIntervalInBackground: false,
    // 503 → degrade silently, do not retry.
    retry: (failureCount, err) => {
      if (err instanceof ApiError && (err.status === 503 || err.status === 400)) return false;
      return failureCount < 2;
    },
    staleTime: 30_000,
  });
}

export function useTVHealth(options?: { enabled?: boolean }) {
  const { token } = useSessionToken();
  const enabled = options?.enabled ?? true;
  return useQuery({
    queryKey: ["tv", "health"],
    queryFn: () => api.get<TVHealth>("/tv/health", { token }),
    enabled: !!token && enabled,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: (failureCount, err) => {
      if (err instanceof ApiError && err.status === 503) return false;
      return failureCount < 2;
    },
    staleTime: 15_000,
  });
}

/**
 * Convenience selector — `true` only when TV health endpoint reports "ok".
 * Used by the live-trading modal as an extra gate before allowing tv_signal
 * instances to go live.
 */
export function useTVHealthOk(): { ok: boolean; loading: boolean; reason: string | null } {
  const q = useTVHealth();
  if (q.isLoading) return { ok: false, loading: true, reason: null };
  if (q.error) {
    const reason =
      q.error instanceof ApiError && q.error.status === 503
        ? "TradingView integration disabled on this deployment"
        : "Could not reach TradingView health endpoint";
    return { ok: false, loading: false, reason };
  }
  const status = q.data?.status ?? "unknown";
  if (status === "ok") return { ok: true, loading: false, reason: null };
  return { ok: false, loading: false, reason: `TradingView health: ${status}` };
}
