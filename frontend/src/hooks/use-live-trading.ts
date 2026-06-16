"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { useSessionToken } from "./use-session-token";
import type {
  GoLiveRequest,
  InstanceHealth,
  InstanceSignal,
  InstanceTrade,
  LiveConsentPublic,
  LiveConsentRequest,
  LiveEligibilityResponse,
  RevertToPaperRequest,
  StrategyInstancePublic,
} from "@/types";

const FALLBACK_GATES: LiveEligibilityResponse = {
  eligible: false,
  required_consent_version: "1.0.0",
  signed_consent_version: null,
  gates: [
    { id: "email_verified", label: "Email verified", passed: false, fix_url: "/verify-email" },
    { id: "totp_enabled", label: "Two-factor enabled", passed: false, fix_url: "/settings" },
    { id: "subscription_active", label: "Active subscription", passed: false, fix_url: "/billing" },
    { id: "backtest_quality", label: "Backtest PF > 1.3, DD < 25%", passed: false, fix_url: "/backtest" },
    { id: "paper_track_record", label: "Paper trading ≥ 14d / ≥ 10 trades", passed: false },
    { id: "broker_connected", label: "Broker connected", passed: false, fix_url: "/broker" },
    { id: "broker_min_balance", label: "Minimum balance reached", passed: false },
    { id: "kill_switch_off", label: "Kill switch off", passed: true },
  ],
};

/** GET /strategy-instances/{id}/live-eligibility — falls back to empty checklist while API is in build. */
export function useLiveEligibility(instanceId: string | null | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["live-eligibility", instanceId],
    queryFn: async () => {
      if (!instanceId) return FALLBACK_GATES;
      try {
        return await api.get<LiveEligibilityResponse>(
          `/strategy-instances/${instanceId}/live-eligibility`,
          { token },
        );
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // Endpoint not yet shipped — surface fallback so UI still renders.
          return FALLBACK_GATES;
        }
        throw err;
      }
    },
    enabled: !!token && !!instanceId,
    staleTime: 30_000,
  });
}

/** POST /live-consents — record the user's risk acknowledgement. */
export function useSignLiveConsent() {
  const { token } = useSessionToken();
  return useMutation({
    mutationFn: (input: LiveConsentRequest) =>
      api.post<LiveConsentPublic, LiveConsentRequest>("/live-consents", input, { token }),
  });
}

/** POST /strategy-instances/{id}/go-live */
export function useGoLive(instanceId: string) {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: GoLiveRequest) =>
      api.post<StrategyInstancePublic, GoLiveRequest>(
        `/strategy-instances/${instanceId}/go-live`,
        input,
        { token },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategy-instances"] });
      qc.invalidateQueries({ queryKey: ["live-eligibility", instanceId] });
    },
  });
}

/** POST /strategy-instances/{id}/revert-to-paper */
export function useRevertToPaper(instanceId: string) {
  const { token } = useSessionToken();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: RevertToPaperRequest) =>
      api.post<StrategyInstancePublic, RevertToPaperRequest>(
        `/strategy-instances/${instanceId}/revert-to-paper`,
        input,
        { token },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["strategy-instances"] }),
  });
}

/** Polling GET /strategy-instances/{id}/health — every 10s by default. */
export function useInstanceHealth(instanceId: string | null | undefined, intervalMs = 10_000) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["instance-health", instanceId],
    queryFn: () =>
      api.get<InstanceHealth>(`/strategy-instances/${instanceId}/health`, { token }),
    enabled: !!token && !!instanceId,
    refetchInterval: intervalMs,
    refetchIntervalInBackground: false,
    retry: 1,
  });
}

export function useInstanceSignals(instanceId: string | null | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["instance-signals", instanceId],
    queryFn: () =>
      api.get<InstanceSignal[]>(`/strategy-instances/${instanceId}/signals`, { token }),
    enabled: !!token && !!instanceId,
    refetchInterval: 15_000,
  });
}

export function useInstanceTrades(instanceId: string | null | undefined) {
  const { token } = useSessionToken();
  return useQuery({
    queryKey: ["instance-trades", instanceId],
    queryFn: () =>
      api.get<InstanceTrade[]>(`/strategy-instances/${instanceId}/trades`, { token }),
    enabled: !!token && !!instanceId,
    refetchInterval: 15_000,
  });
}
